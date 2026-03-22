"""
main.py - FastAPI entry point for the Canadian News App
Exposes GET /news which returns summarized news from Canadian RSS feeds.
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before other imports (OPENAI_API_KEY, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import (
    count_articles,
    count_pending_articles,
    get_articles_page,
    get_articles_top,
    init_db,
    save_news_items,
)
from services.fetch_news import fetch_all_feeds
from services.page_summaries import fill_pending_summaries
from services.page_summary_coordinator import (
    REQUEST_POLL_WAIT_SECONDS,
    release_page_summarize,
    short_wait_for_page_summaries_ready,
    try_acquire_page_summarize,
)
from services.ranking import compute_rank_score, log_rank_debug_top
from services.story_clustering import cluster_articles
from services.summarize import quick_fallback_summary

PAGE_SIZE = 5
TOP_STORIES_LIMIT = 3

# After serving page N, only prewarm pages N+1 … N+MAX_PREWARM_AHEAD (not beyond).
MAX_PREWARM_AHEAD = 2

# Public JSON shape for /news (no internal DB-only fields).
_ARTICLE_PUBLIC_KEYS = (
    "id",
    "title",
    "summary",
    "source",
    "link",
    "published",
    "category",
    "region",
    "image_url",
    "sources",
    "related_links",
    "cluster_id",
)


def _public_article(row: dict) -> dict:
    return {k: row.get(k) for k in _ARTICLE_PUBLIC_KEYS}


app = FastAPI(title="Canada Brief API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


@app.on_event("startup")
def startup():
    init_db()


def _strip_rss_excerpt(row: dict) -> None:
    row.pop("rss_excerpt", None)


def _ensure_summary_fallback(row: dict) -> None:
    """If summary text is missing, use local title-based fallback (empty DB edge case)."""
    s = (row.get("summary") or "").strip()
    if s:
        return
    row["summary"] = quick_fallback_summary(row.get("title") or "")


def _pending_rss_or_title_fallback(row: dict) -> None:
    """
    For pending rows in JSON responses: prefer rss_excerpt (truncated), else title heuristic.
    Does not call the LLM.
    """
    status = (row.get("summary_status") or "pending").strip().lower()
    if status != "pending":
        return
    ex = (row.get("rss_excerpt") or "").strip()
    if len(ex) >= 40:
        cut = ex[:1200].strip()
        row["summary"] = cut + ("..." if len(ex) > 1200 else "")
        return
    row["summary"] = quick_fallback_summary(row.get("title") or "")


def _count_pending(rows: list) -> int:
    n = 0
    for r in rows:
        if (r.get("summary_status") or "pending").strip().lower() == "pending":
            n += 1
    return n


def _unique_rows_page_first(page_rows: list, top_rows: list) -> list:
    """
    One row per id: all of page 1 first, then top stories not already included.
    Avoids summarizing the same story twice when top stories overlap page 1.
    """
    seen = set()
    out = []
    for r in page_rows:
        rid = r.get("id")
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    for r in top_rows:
        rid = r.get("id")
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


def _pregenerate_page1_and_top_stories() -> tuple[int, int, int]:
    """
    LLM-summarize page 1 and top stories only (deduped). Used by background prewarm.
    Returns (n_ready, n_failed, pending_remaining_in_db).
    """
    page_rows = get_articles_page(0, PAGE_SIZE)
    top_rows = get_articles_top(TOP_STORIES_LIMIT)
    combined = _unique_rows_page_first(page_rows, top_rows)
    ready_n, failed_n = fill_pending_summaries(combined, max_count=None)
    pending_left = count_pending_articles()
    return ready_n, failed_n, pending_left


def _background_prewarm_worker() -> None:
    """Runs after ingest; does not block HTTP."""
    print("[prewarm] background started (page1 + top stories, deduped)")
    t0 = time.time()
    try:
        pr, pf, pend_left = _pregenerate_page1_and_top_stories()
        elapsed = time.time() - t0
        print(
            f"[prewarm] background finished time_s={elapsed:.3f} "
            f"summaries_ready={pr} summaries_failed={pf} pending_remaining={pend_left}"
        )
    except Exception as e:
        print(f"[prewarm] background failed: {e}")


def _schedule_prewarm_after_ingest() -> None:
    """Fire-and-forget thread: fills page-1 + top LLM summaries after DB save."""
    t = threading.Thread(target=_background_prewarm_worker, daemon=True)
    t.start()
    print("[prewarm] background task scheduled (non-blocking)")


def _prewarm_page_worker(target_page: int, page_size: int, total_rows: int) -> None:
    """
    Summarize one API page (1-based) in the background.
    Skips if out of range, nothing pending, or lock not available.
    """
    offset = (target_page - 1) * page_size
    if total_rows <= 0 or offset >= total_rows:
        print(f"[prewarm] skip page={target_page} reason=exceeds_limit")
        return

    rows = get_articles_page(offset, page_size)
    if not rows:
        print(f"[prewarm] skip page={target_page} reason=exceeds_limit")
        return

    if _count_pending(rows) == 0:
        print(f"[prewarm] skip page={target_page} reason=already_ready")
        return

    if not try_acquire_page_summarize(target_page):
        print(f"[lock] prevented duplicate page={target_page}")
        print(f"[prewarm] skip page={target_page} reason=in_flight")
        return

    print(f"[prewarm] started page={target_page}")
    t0 = time.time()
    try:
        rows = get_articles_page(offset, page_size)
        if _count_pending(rows) == 0:
            print(f"[prewarm] skip page={target_page} reason=already_ready")
            return
        n_ready, n_failed = fill_pending_summaries(rows, max_count=None)
        elapsed = time.time() - t0
        print(
            f"[prewarm] finished page={target_page} "
            f"summaries_ready={n_ready} summaries_failed={n_failed} time_s={elapsed:.3f}"
        )
    except Exception as e:
        print(f"[prewarm] error page={target_page}: {e}")
    finally:
        release_page_summarize(target_page)


def _schedule_prewarm_ahead(served_page: int, page_size: int, total_rows: int) -> None:
    """
    After serving page `served_page`, only prewarm pages served_page+1 … served_page+MAX_PREWARM_AHEAD.
    No chaining beyond that (each request schedules at most two targets).
    """
    for k in range(1, MAX_PREWARM_AHEAD + 1):
        target = served_page + k
        offset = (target - 1) * page_size
        if offset >= total_rows:
            print(f"[prewarm] skip page={target} reason=exceeds_limit")
            continue
        t = threading.Thread(
            target=_prewarm_page_worker,
            args=(target, page_size, total_rows),
            daemon=True,
        )
        t.start()


def _run_page_summaries_background(page: int, offset: int, page_size: int) -> None:
    """LLM fill for one page; always releases the page lock."""
    try:
        rows = get_articles_page(offset, page_size)
        n_ready, n_failed = fill_pending_summaries(rows, max_count=None)
        print(
            f"[page_summarize] background finished page={page} "
            f"summaries_ready={n_ready} summaries_failed={n_failed}"
        )
    except Exception as e:
        print(f"[page_summarize] background page={page} error: {e}")
    finally:
        release_page_summarize(page)


def _run_ingest() -> tuple[int, int, int, float]:
    """
    Refresh pipeline: fetch → dedupe → cluster → rank → save.
    Does not wait for LLM — page-1 prewarm runs in a background thread.
    """
    t0 = time.time()
    raw_items = fetch_all_feeds()
    n_ingress = len(raw_items)
    clustered = cluster_articles(raw_items)
    n_cluster = len(clustered)
    now = datetime.now(timezone.utc).isoformat()
    for row in clustered:
        row["summary"] = ""
        row["summary_status"] = "pending"
        row["rank_score"] = compute_rank_score(row)
        row["last_updated_at"] = now
        ex = row.get("rss_excerpt") or ""
        row["rss_excerpt"] = str(ex)[:12000]
    log_rank_debug_top(clustered, limit=10)
    save_news_items(clustered)

    ingest_elapsed = time.time() - t0
    print(
        f"[ingest] ingest_complete (fetch+cluster+rank+save) time_s={ingest_elapsed:.3f} "
        f"(LLM prewarm not included — runs in background)"
    )
    _schedule_prewarm_after_ingest()
    print(
        f"[/news] ingest done: ingress_to_cluster={n_ingress} "
        f"clusters_saved={n_cluster} ingest_path_s={time.time() - t0:.3f}"
    )
    return n_ingress, n_cluster, n_cluster, ingest_elapsed


@app.get("/news")
def get_news(
    refresh: bool = False,
    page: int = 1,
    page_size: int = PAGE_SIZE,
):
    """
    Paginated feed: JSON object with "articles" and "top_stories".

    After ingest/cold-start, page 1 skips synchronous LLM; fallbacks until background prewarm.

    Request path never runs LLM synchronously. If another worker holds the page lock,
    responses use RSS/title fallbacks immediately. Otherwise a short DB poll (after
    scheduling background fill) may return ready summaries without blocking on LLM.
    """
    t_start = time.time()
    page = max(1, int(page))
    page_size = min(PAGE_SIZE, max(1, int(page_size)))

    n_ingress = n_cluster = n_saved = 0
    ingest_elapsed_s = 0.0

    if refresh:
        refresh_mode = "ingest"
        print("[/news] refresh mode ON — ingest pipeline")
        try:
            n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ingest failed: {e}") from e
    elif count_articles() == 0:
        refresh_mode = "cold_start"
        print("[/news] DB empty — cold-start ingest")
        try:
            n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ingest failed: {e}") from e
    else:
        refresh_mode = "read"
        print("[/news] serving from SQLite")

    total = count_articles()
    offset = (page - 1) * page_size

    t_read = time.time()
    page_rows = get_articles_page(offset, page_size)
    top_stories = get_articles_top(TOP_STORIES_LIMIT)
    read_elapsed = time.time() - t_read

    n_page = len(page_rows)
    pending_on_page = _count_pending(page_rows)
    page1_warm_before_lazy = page == 1 and pending_on_page == 0

    skip_lazy_fill = page == 1 and refresh_mode in ("ingest", "cold_start")

    t_lazy = time.time()
    n_ready = 0
    n_failed = 0

    if skip_lazy_fill:
        pass
    elif pending_on_page > 0:
        if not try_acquire_page_summarize(page):
            print(f"[lock] prevented duplicate page={page}")
            print(f"[request] fallback_used page={page} reason=in_flight")
        else:
            threading.Thread(
                target=_run_page_summaries_background,
                args=(page, offset, page_size),
                daemon=True,
            ).start()
            page_rows, wait_ok = short_wait_for_page_summaries_ready(page, page_size)
            if wait_ok:
                print(
                    f"[/news] page={page} request poll succeeded within "
                    f"{REQUEST_POLL_WAIT_SECONDS:.2f}s — returning DB summaries"
                )
            else:
                print(f"[request] fallback_used page={page} reason=timeout")
    lazy_elapsed = time.time() - t_lazy

    for row in top_stories:
        _pending_rss_or_title_fallback(row)
        _ensure_summary_fallback(row)
        _strip_rss_excerpt(row)

    for row in page_rows:
        _pending_rss_or_title_fallback(row)
        _ensure_summary_fallback(row)
        _strip_rss_excerpt(row)

    total_elapsed = time.time() - t_start
    warm_flag = f" page1_warm_before_lazy={page1_warm_before_lazy}" if page == 1 else ""
    skip_flag = f" lazy_fill_skipped={skip_lazy_fill}" if page == 1 else ""
    ingest_flag = (
        f" ingest_path_s={ingest_elapsed_s:.3f}" if ingest_elapsed_s > 0 else ""
    )
    print(
        f"[/news] page={page} page_size_used={page_size} max_page_size={PAGE_SIZE} "
        f"page_articles_loaded={n_page}{warm_flag}{skip_flag} "
        f"pending_on_page_before={pending_on_page} summaries_ready_on_request={n_ready} "
        f"summaries_failed_on_request={n_failed} refresh_mode={refresh_mode}{ingest_flag} "
        f"db_read_s={read_elapsed:.3f} lazy_s={lazy_elapsed:.3f}s request_total_s={total_elapsed:.3f}s "
        f"(ingest/prewarm threads not included) ingress={n_ingress} saved={n_saved}"
    )

    payload = {
        "articles": [_public_article(r) for r in page_rows],
        "top_stories": [_public_article(r) for r in top_stories],
    }
    _schedule_prewarm_ahead(page, page_size, total)

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Total-Count": str(total)},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
