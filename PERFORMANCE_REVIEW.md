# Performance Architecture Review — Canada Brief (News App)

**Scope:** FastAPI backend (`backend/`), Next.js frontend (`frontend/`), SQLite (`news.db`).  
**Audience:** Engineers shipping or operating this codebase.  
**Method:** Static analysis of request paths, ingestion, and UI data flow as implemented in-repo (March 2025).

---

## 1. Executive Summary

The app feels slow primarily because **the first page load intentionally triggers a full news pipeline** (RSS → dedupe → optional image HTTP fetches → clustering → DB replace → **then** per-article AI summaries) **inside the same HTTP request** that the browser is waiting on. Secondary factors: **sequential RSS fetching**, **sequential OpenAI (or fallback) summarization** for every pending row on the visible page, **full table clear + bulk insert** on each refresh, and **clustering cost** (TF‑IDF + hierarchical clustering locally, or a **large embedding batch** to OpenAI when configured).

**Bottlenecks ranked by typical user-visible impact (highest first):**

| Rank | Bottleneck | Why it hurts |
|------|------------|--------------|
| 1 | **Synchronous full ingest on first `/news?page=1`** | `refresh=true` runs `_run_ingest()` before any cached read; user waits for network I/O, CPU, clustering, and DB write. |
| 2 | **`fill_pending_summaries()` on the hot path** | After DB read, each pending article may call `summarize_title()` → OpenAI chat with **30s timeout**, **one row at a time** (`page_summaries.py`). |
| 3 | **Sequential RSS in `fetch_all_feeds()`** | ~15 feeds fetched **one after another** (`fetch_news.py`), each up to 5s timeout — worst case adds many seconds before clustering even starts. |
| 4 | **Clustering at ingest** | Up to `MAX_INGEST_ARTICLES` (150) items: `AgglomerativeClustering` + TF‑IDF, or embedding API with **60s timeout** (`story_clustering.py`). |
| 5 | **Image scraping** | Up to 8 sequential article-page `requests.get` + BeautifulSoup for `og:image` (`fetch_news.py`). |
| 6 | **DB write pattern** | `save_news_items` clears the entire `news` table then inserts all rows (`database.py`) — fine at MVP scale but blocks longer than incremental upserts would. |

Smaller but real: multiple SQLite connections per request (no pool), `count_articles()` plus two overlapping reads (`get_articles_page` + `get_articles_top`), and frontend `cache: "no-store"` on every fetch.

---

## 2. Request Flow Analysis

### End-to-end path (typical)

1. **Browser** loads Next.js app → `NewsFeed` mounts (`frontend/app/page.tsx` → `frontend/components/NewsFeed.tsx`).
2. **`loadCurrentPage`** runs (`useEffect` depends on `loadCurrentPage`). For **page 1 only**, the **first** successful load sets `refresh: true` (`firstPageRefreshRef`).
3. **`fetchNewsPage`** (`frontend/lib/api.ts`) calls `GET {API}/news?page=&page_size=&refresh=` with **`cache: "no-store"`** (no browser/CDN caching).
4. **Backend `get_news`** (`backend/main.py`):
   - If `refresh` **or** DB empty → **`_run_ingest()`** (blocking).
   - Else → log “serving from SQLite” and skip ingest.
   - **`count_articles()`** for total and pagination header.
   - **`get_articles_page(offset, limit)`** — one page, ordered by `rank_score`.
   - **`get_articles_top(TOP_STORIES_LIMIT)`** — top 3 by same ordering (duplicate query pattern vs first page).
   - **`fill_pending_summaries(page_rows)`** — may call OpenAI per row, **sequential**.
   - If some top stories are not on the current page, **`fill_pending_summaries(top_extra)`** — more sequential work.
   - Strip `rss_excerpt`, ensure fallback summary text, return JSON.

### Where time goes (conceptual)

- **Refresh / cold path:** dominated by **feed fetch wall time** + **clustering** + **DB replace** + **lazy summaries** (if many rows still `pending`).
- **Warm path (page 2+, or page 1 after first load):** dominated by **`fill_pending_summaries`** if summaries are not yet `ready`, plus modest SQLite reads. Ingest is skipped.

### Blocking operations on the request path

| Phase | Blocking? | Location |
|-------|-----------|----------|
| RSS HTTP | Yes | `fetch_all_feeds` |
| Dedupe / sort / cap | Yes (CPU) | `fetch_all_feeds` |
| Image page fetch | Yes (HTTP) | `_extract_image_from_article_page` (up to 8) |
| Embeddings or TF‑IDF + clustering | Yes | `cluster_articles` |
| Rank + save | Yes | `_run_ingest` → `save_news_items` |
| DB read page + top | Yes | `get_articles_page`, `get_articles_top` |
| AI summary per article | Yes | `fill_pending_summaries` → `summarize_title` |

Nothing in `get_news` offloads work to a background queue; the client waits for the full chain.

---

## 3. Backend Bottlenecks

### Feed fetching (`backend/services/fetch_news.py`)

- **Sequential loop** over `FEEDS` (Canadian + world feeds). Each `requests.get` uses `REQUEST_TIMEOUT = 5`. Total wall time is roughly the **sum** of per-feed latencies (minus OS overlap — there is none in code).
- **Parsing** uses `feedparser` per feed; moderate CPU.
- **Dedupe** is a single pass (cheap): normalized link + normalized title sets.
- **Cap** `MAX_INGEST_ARTICLES = 150` limits downstream work but **after** all feeds are fetched.

### Deduplication

- **Cost:** Low (in-memory sets). Not a major factor.
- **Semantics:** Conservative (exact normalized title / link), so clustering still sees many near-duplicates — shifting work to clustering rather than dedupe.

### Clustering (`backend/services/story_clustering.py`)

- **When:** Only during ingest (`main.py` → `cluster_articles`), not on every read.
- **OpenAI path:** If `OPENAI_API_KEY` is set, **`_fetch_openai_embeddings`** batches all cluster texts in **one** HTTP POST (`timeout=60`), then `AgglomerativeClustering` on dense matrices — **CPU + memory** grow with article count.
- **Fallback:** TF‑IDF on **titles only** (`TfidfVectorizer` + same clustering) — no network, still **O(n²)-ish** clustering behavior for larger *n*.
- **Comment in file** states clustering runs after refresh fetch, not on cached reads — accurate.

### Ranking (`backend/services/ranking.py`)

- **Cost:** Per-row math only; negligible vs I/O and LLM calls.

### Image scraping (`fetch_news.py`)

- After dedupe, for the **newest** `IMAGE_SCRAPE_MAX_ARTICLES = 8` items **without** RSS images, the code fetches the **article HTML** and parses `og:image` / twitter / `<img>`. Each fetch uses `IMAGE_PAGE_TIMEOUT = 4`.
- **Impact:** Up to ~32s worst-case for images alone (unlikely in practice, but sequential).

### AI summarization (`backend/services/summarize.py`, `page_summaries.py`)

- **Ingest** sets `summary` to `quick_fallback_summary` and `summary_status` to **`pending`** (`main.py`). Real AI is deferred — good intention.
- **On read**, `fill_pending_summaries` runs **`summarize_title`** for each pending row. With API key, that is **`requests.post` to OpenAI** with `_OPENAI_TIMEOUT = 30` **per article**, **sequentially** in a `for` loop.
- **Worst case:** First visit after ingest could summarize **up to `page_size` (default 5)** plus **extra top-story rows** not on the page — still sequential, so latency **adds**.

### Database reads / writes (`backend/database.py`)

- **Reads:** `get_articles_page` / `get_articles_top` use proper `LIMIT`/`OFFSET` — not loading the full table for the page.
- **Writes:** `save_news_items` → **`clear_articles()`** (`DELETE FROM news`) then **`INSERT`** all cluster rows. Every refresh **replaces the entire dataset** — simple but **heavy** and prevents incremental updates.
- **Updates:** `update_article_summary_fields` runs **once per summarized article** during a request — each opens a **new connection** and `commit()` — fine at low QPS but adds round-trips under load.
- **No indexes** called out in schema for `rank_score` / `published` — SQLite may still be fast at hundreds of rows; at larger scale, indexing would matter.

### Work ordering

- **Sensible:** RSS and clustering before persist; lazy summaries after read.
- **Problematic:** **Full ingest tied to user navigation** (see frontend) and **summaries still blocking the response** after DB read. Image scraping happens **before** clustering — could be deferred or dropped under time budget (not implemented).

---

## 4. Frontend Bottlenecks

### Initial page load

- Next.js client bundle + hydration; no special dynamic imports observed for the feed.
- **First API call uses `refresh=true`** — this is the dominant cost, not React.

### API calling strategy (`frontend/lib/api.ts`)

- **`cache: "no-store"`** on every `fetch` — correct for “always fresh” semantics but **prevents** HTTP caching of `/news` responses (no CDN/browser reuse).

### Refresh behavior (`frontend/components/NewsFeed.tsx`)

- **`firstPageRefreshRef`:** The **first** successful load of **page 1** passes **`refresh: true`**. That triggers **full backend ingest** once per session (until “Try again” resets the ref).
- **User expectation mismatch:** A normal “load the app” feels like “show me cached news quickly” but the code **prioritizes a full refresh** on first paint.

### Pagination

- Page 2+ uses **`refresh: false`** — avoids ingest; **much faster** path if DB already populated.
- Changing `page` triggers `loadCurrentPage` again — expected; no evidence of prefetching page N+1.

### Top stories / spotlight

- Backend returns **`top_stories`** in the JSON envelope (`main.py` payload).
- The UI **does not use `result.topStories`** from the API. Instead it computes **`pickMixedTopStories(filtered, 3)`** on **client-filtered** `articles` (`NewsFeed.tsx` + `pickMixedTopStories.ts`).
- **Consequence:** Backend still **queries** top rows and may **summarize** “extra” top stories not on the page — **work the current UI never displays from the API**, increasing latency without matching UX (unless you later wire `topStories`).

### Unnecessary re-fetches

- **`reloadNonce`** + resetting **`firstPageRefreshRef`** on “Try again” forces **another full refresh** — appropriate for recovery but expensive.
- Filters (`filterArticles`) only affect display; they do not refetch — good.

---

## 5. Structural Problems

1. **Ingestion and presentation are not separated.** The same **`GET /news`** endpoint both **refreshes the world** (optional) and **serves the page**. That couples **slow batch work** to **read latency**.

2. **“Lazy” summaries are still synchronous to the HTTP response.** They are lazy relative to ingest (good) but not relative to the client (bad for TTFB). The handler **awaits** `fill_pending_summaries`.

3. **First-load refresh by default** (`NewsFeed`) guarantees the **worst** backend path for the **most common** user action (open app).

4. **Spotlight data path is duplicated/misaligned:** server computes `top_stories` + extra summary work; client computes its own top three from the page slice. This is a **coherence and performance** smell.

5. **No queue / worker.** Long tasks (ingest, batch embeddings, bulk summarization) have no home outside the API process.

6. **SQLite + full replace** is a valid MVP, but it **amplifies** refresh cost (full delete + insert) and makes **partial updates** (single new article) impossible without schema/workflow changes.

---

## 6. Data Flow Problems

| Question | In this repo |
|----------|----------------|
| Fetching too much? | **Yes at ingest:** all feeds every refresh, up to 150 articles clustered. **No for pagination:** page query is limited. |
| Summarizing too much? | **Potentially yes:** up to page size + extra top rows per request, sequentially, each possibly hitting OpenAI. |
| Clustering too often? | **Once per refresh**, not per page view — acceptable if refresh were rare; **not acceptable** if refresh runs on every first visit. |
| Limiting too early or late? | Dedupe then sort then **`[:MAX_INGEST_ARTICLES]`** — reasonable. Image scrape only on capped list’s head — good. |
| DB inefficient? | **Full clear + insert** on refresh; **multiple connections** per request; many **UPDATE**s during summary fill. |

---

## 7. What Should Be Fast vs Slow

**Should feel instant (target &lt; ~100–300 ms server time for warm reads):**

- `GET /news` with **`refresh=false`** when data exists and summaries are already **`ready`**.
- Simple SQLite `SELECT` with `LIMIT` for a page.
- Returning JSON without waiting on external LLMs.

**Can be slower if clearly asynchronous (user not blocked):**

- Full RSS crawl across many feeds.
- Embedding + clustering batch.
- Optional hero-image scraping.
- Backfilling summaries for items not on screen.

**Should not block the initial HTML/API response (or should be strictly budgeted):**

- OpenAI chat completions for summaries — better as **background jobs** or **on-demand with streaming**, not **N sequential blocking calls** in `get_news`.

---

## 8. Recommended Architecture (Conceptual)

**Ideal separation:**

1. **Ingestion pipeline (scheduler / worker / cron):** Pull feeds → dedupe → cluster → rank → **upsert** into DB. Run on an interval or manual “Refresh” action that **does not** block read traffic. Emit metrics (duration, rows changed).

2. **Read API (Fast):** `GET /news` reads **only** precomputed rows, returns immediately. Optionally include `summary_status` so the UI can show a skeleton and poll or use SSE/WebSocket for “summary ready” (future).

3. **Summary worker:** Consumes “pending” rows from a queue or scans in batches; calls OpenAI with **concurrency limit** and **rate limiting**. Updates `summary` + `summary_status`.

4. **Frontend:**  
   - Default first load: **`refresh=false`** (or a dedicated **`POST /admin/refresh`**).  
   - Show last-good data instantly; **optional** background poll for “new data available.”  
   - Use **`top_stories` from API** OR remove server-side top query to avoid duplicate work.

5. **Caching:** Short TTL HTTP cache or CDN for **`GET /news?refresh=false`** if responses are identical for many users; keep **`no-store`** only for admin refresh. Consider **ETag**/`If-None-Match` for repeat navigations.

6. **RSS fetch:** **Parallelize** with `asyncio` + bounded concurrency or thread pool; respect global timeout and per-host limits.

This preserves the product (ranked feed, summaries, clustering) while **moving latency** from the user’s critical path to **batch and async** paths.

---

## 9. Priority Fixes

### Highest impact / lowest effort

1. **Stop defaulting `refresh=true` on first page load** (`NewsFeed.tsx`). Use **`refresh=false`** for first paint; offer explicit “Refresh news” that calls `refresh=true` or a dedicated ingest endpoint. **Expected:** First load drops from **many seconds** to **DB + summary** time only; often **order-of-magnitude** improvement for first paint.

2. **Cap or defer `fill_pending_summaries`** on the read path — e.g. summarize **at most 1–2** rows per request, or return `pending` and summarize in background. **Expected:** Large reduction in **tail latency** when many rows are pending.

3. **Use or remove server `top_stories`:** Either wire **`result.topStories`** in the UI and align filtering, or **remove** `get_articles_top` + `top_extra` summary work. **Expected:** Fewer sequential LLM calls and DB reads per request.

### Highest impact / medium effort

4. **Parallel RSS fetches** with a concurrency limit (`fetch_all_feeds`). **Expected:** Feed phase wall time closer to **max(feed)** than **sum(feed)** — often **2–5×** faster for many feeds.

5. **Background ingestion job** (separate process or thread with a job lock) triggered by timer or admin API; **`GET /news` never calls `_run_ingest`**. **Expected:** Stable **p95 read latency** regardless of ingest duration.

6. **Incremental DB writes** (upsert by `link` or cluster id) instead of **truncate + insert**. **Expected:** Shorter write locks and less I/O on each refresh.

### Long-term improvements

7. **Dedicated worker + queue** for summaries and optional embedding/clustering at scale.

8. **Connection pooling** or single connection per request scope for SQLite writes.

9. **Observability:** structured logs/metrics for ingest duration, summary queue depth, OpenAI error rate.

---

## 10. Code Hotspots

| Location | Role | Why it’s a hotspot |
|----------|------|---------------------|
| `backend/main.py` — `get_news`, `_run_ingest` | Orchestrates ingest + read + summaries | Single place where **slow paths stack**; `refresh` and `fill_pending_summaries` dominate latency. |
| `backend/services/fetch_news.py` — `fetch_all_feeds` | RSS + dedupe + image scrape | **Sequential** network I/O; optional **8** article page fetches. |
| `backend/services/story_clustering.py` — `cluster_articles`, `_fetch_openai_embeddings` | Clustering | **Heavy CPU** (TF‑IDF + hierarchical) or **large API call** (embeddings). |
| `backend/services/page_summaries.py` — `fill_pending_summaries` | Lazy summaries | **Sequential** `summarize_title` + DB update per row. |
| `backend/services/summarize.py` — `_openai_summarize` | OpenAI chat | **Up to 30s** per call; multiplies with row count. |
| `backend/database.py` — `save_news_items`, `update_article_summary_fields` | Persistence | **Full table clear**; **per-row** commits on summary updates. |
| `frontend/components/NewsFeed.tsx` — `loadCurrentPage`, `firstPageRefreshRef` | When refresh runs | Forces **full ingest** on first successful page-1 load. |
| `frontend/lib/api.ts` — `fetchNewsPage` | HTTP client | **`cache: "no-store"`** — prevents any HTTP-level reuse. |

---

## 11. Final Recommendation

**The best practical next step for this codebase is to change the frontend contract so the default first request does not pass `refresh=true`**, and to **strictly limit or move off the request path** the work in `fill_pending_summaries` (batch size 1–2 or background worker). Together, these align user-perceived speed with the architecture you already sketched (lazy summaries at ingest, fast reads) without requiring a full rewrite.

After that, **parallelize RSS** and **stop duplicating spotlight work** (use API `top_stories` or drop the server query) for the next increment of wins.

---

## Uncertainties / assumptions

- Exact timings depend on **network**, **OpenAI** latency, and **machine CPU**; not benchmarked in this review.
- If `OPENAI_API_KEY` is **unset**, summary path uses **local** rules in `summarize_title` — still **sequential** but much faster than API calls; perceived slowness may then be **almost entirely ingest + clustering**.
- Production deployment (single vs multi-worker, reverse proxy timeouts) was not inspected; **very long** `get_news` responses may also hit **proxy timeouts** — worth validating if issues persist after code changes.
