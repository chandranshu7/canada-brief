"""
main.py - FastAPI entry point for the Canadian News App
Exposes GET /news which returns summarized news from Canadian RSS feeds.
"""

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load backend/.env before other imports (DATABASE_URL, OPENAI_API_KEY, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from env import get_openai_api_key
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
    release_story_buffer_prewarm,
    short_wait_for_page_summaries_ready,
    try_acquire_page_summarize,
    try_acquire_story_buffer_prewarm,
)
from services.ranking import compute_rank_score, log_rank_debug_top
from services.story_clustering import cluster_articles
from services.summarize import clean_summary, normalize_stored_summary, quick_fallback_summary

PAGE_SIZE = 5
TOP_STORIES_LIMIT = 3

# Story-buffer prewarm: keep the next N-ranked stories after `cursor` summarized (not full pages).
STORY_BUFFER_AHEAD = 2

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
    """Public JSON shape; summary always length-normalized (legacy DB rows included)."""
    d = {k: row.get(k) for k in _ARTICLE_PUBLIC_KEYS}
    if isinstance(d.get("summary"), str):
        d["summary"] = clean_summary(d["summary"] or "")
    return d


def _log_startup_config() -> None:
    """Log database backend and whether OPENAI_API_KEY is set (never log secret values)."""
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if db_url:
        print("[startup] database backend: PostgreSQL (SQLAlchemy + psycopg)")
    else:
        print(
            "[startup] database backend: SQLite (local news.db — "
            "set DATABASE_URL on Render/production)"
        )
    print(f"[startup] DATABASE_URL: {'set' if db_url else 'not set (SQLite fallback)'}")
    openai_ok = bool(get_openai_api_key())
    print(f"[startup] OPENAI_API_KEY: {'present' if openai_ok else 'absent'}")


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
    _log_startup_config()
    init_db()


def _strip_rss_excerpt(row: dict) -> None:
    row.pop("rss_excerpt", None)


def _ensure_summary_fallback(row: dict) -> None:
    """If summary text is missing, use local title-based fallback (empty DB edge case)."""
    s = (row.get("summary") or "").strip()
    if s:
        return
    row["summary"] = quick_fallback_summary(row.get("title") or "")  # normalized in summarize.py


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
        raw = cut + ("..." if len(ex) > 1200 else "")
        row["summary"] = normalize_stored_summary(
            raw,
            row.get("title") or "",
            (row.get("rss_excerpt") or "").strip() or None,
        )
        return
    row["summary"] = quick_fallback_summary(row.get("title") or "")


def _count_pending(rows: list) -> int:
    n = 0
    for r in rows:
        if (r.get("summary_status") or "pending").strip().lower() == "pending":
            n += 1
    return n


def _row_pending_llm(row: dict) -> bool:
    """True if this row still needs an LLM summary (cached ready/failed are skipped)."""
    return (row.get("summary_status") or "pending").strip().lower() == "pending"


def _row_buffer_satisfied(row: dict) -> bool:
    """True if summary is ready or failed (stored fallback) — counts toward buffer readiness."""
    return not _row_pending_llm(row)


def _max_page_number(total_rows: int, page_size: int) -> int:
    """Last valid 1-based page index (0 if no rows). Uses ceiling division."""
    if total_rows <= 0 or page_size <= 0:
        return 0
    return (total_rows + page_size - 1) // page_size


def _ingest_initial_story_buffer() -> tuple[int, int, int]:
    """
    After ingest: warm the first three stories in feed order (rank_score DESC).
    Matches one-story-at-a-time UX: current + next two in global rank.
    """
    rows = get_articles_page(0, 3)
    pending = [r for r in rows if _row_pending_llm(r)]
    if not pending:
        return 0, 0, count_pending_articles()
    ready_n, failed_n = fill_pending_summaries(pending, max_count=None)
    pending_left = count_pending_articles()
    return ready_n, failed_n, pending_left


def _background_prewarm_worker() -> None:
    """Runs after ingest; does not block HTTP."""
    print("[story_prewarm] ingest background started (first 3 stories in feed order)")
    t0 = time.time()
    try:
        pr, pf, pend_left = _ingest_initial_story_buffer()
        elapsed = time.time() - t0
        print(
            f"[story_prewarm] ingest background finished time_s={elapsed:.3f} "
            f"summaries_ready={pr} summaries_failed={pf} pending_remaining={pend_left}"
        )
    except Exception as e:
        print(f"[story_prewarm] ingest background failed: {e}")


def _schedule_prewarm_after_ingest() -> None:
    """Fire-and-forget thread: fills first story-buffer LLM summaries after DB save."""
    t = threading.Thread(target=_background_prewarm_worker, daemon=True)
    t.start()
    print("[story_prewarm] ingest background task scheduled (non-blocking)")


def _story_buffer_prewarm_worker(cursor: int, total_rows_hint: int) -> None:
    """
    Ensure the next STORY_BUFFER_AHEAD stories after `cursor` have summaries (ready or failed).
    Only fills pending rows; skips cached ready/failed. Single-flight via coordinator.
    """
    if not try_acquire_story_buffer_prewarm():
        print("[story_prewarm] skip reason=in_flight")
        return
    try:
        total_rows = count_articles()
        cursor = max(0, min(cursor, max(0, total_rows - 1)))
        if total_rows <= 0:
            print(f"[story_prewarm] skip cursor={cursor} total_rows=0")
            return
        if cursor + 1 >= total_rows:
            print(
                f"[story_prewarm] skip cursor={cursor} no_stories_ahead "
                f"total_rows={total_rows} (hint was {total_rows_hint})"
            )
            return

        ahead = get_articles_page(cursor + 1, STORY_BUFFER_AHEAD)
        ready_count = sum(1 for r in ahead if _row_buffer_satisfied(r))
        pending = [r for r in ahead if _row_pending_llm(r)]

        print(
            f"[story_prewarm] cursor={cursor} total_rows={total_rows} "
            f"ready_ahead_buffer={ready_count}/{len(ahead)} pending_in_buffer={len(pending)}"
        )

        if not pending:
            print("[story_prewarm] skip reason=already_ready")
            return

        n_ready, n_failed = fill_pending_summaries(pending, max_count=len(pending))
        print(
            f"[story_prewarm] done cursor={cursor} prewarmed_ready={n_ready} "
            f"prewarmed_failed={n_failed}"
        )
    except Exception as e:
        print(f"[story_prewarm] error: {e}")
    finally:
        release_story_buffer_prewarm()


def _schedule_story_buffer_prewarm(cursor: int, total_rows: int) -> None:
    """Fire-and-forget: fill next STORY_BUFFER_AHEAD stories after cursor (global feed index)."""
    t = threading.Thread(
        target=_story_buffer_prewarm_worker,
        args=(cursor, total_rows),
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
    Does not wait for LLM — initial story-buffer prewarm runs in a background thread.
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
        f"(LLM story-buffer prewarm not included — runs in background)"
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
    cursor: Optional[int] = None,
):
    """
    Paginated feed: JSON object with "articles" and "top_stories".

    After ingest/cold-start, page 1 skips synchronous LLM; fallbacks until background prewarm.

    Request path never runs LLM synchronously. If another worker holds the page lock,
    responses use RSS/title fallbacks immediately. Otherwise a short DB poll (after
    scheduling background fill) may return ready summaries without blocking on LLM.

    `cursor` is the 0-based global index of the current story in feed order (rank_score DESC).
    Defaults to the first story on this page: (page-1)*page_size. Used for story-buffer prewarm
    (next two stories ahead), not full-page prewarm.
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
        print("[/news] serving from database")

    total = count_articles()
    offset = (page - 1) * page_size
    if cursor is None:
        story_cursor = offset
    else:
        story_cursor = max(0, int(cursor))

    t_read = time.time()
    page_rows = get_articles_page(offset, page_size)
    top_stories = get_articles_top(TOP_STORIES_LIMIT)
    read_elapsed = time.time() - t_read

    print(
        f"[/news] db_page_query total_rows={total} offset={offset} limit={page_size} "
        f"rows_returned={len(page_rows)} max_allowed_page={_max_page_number(total, page_size)}"
    )

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

    n_page = len(page_rows)
    print(
        f"[/news] page_rows_final total_rows={total} offset={offset} limit={page_size} "
        f"rows_returned={n_page}"
    )

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
        f"story_cursor={story_cursor} "
        f"page_articles_loaded={n_page}{warm_flag}{skip_flag} "
        f"pending_on_page_before={pending_on_page} summaries_ready_on_request={n_ready} "
        f"summaries_failed_on_request={n_failed} refresh_mode={refresh_mode}{ingest_flag} "
        f"db_read_s={read_elapsed:.3f} lazy_s={lazy_elapsed:.3f}s request_total_s={total_elapsed:.3f}s "
        f"(ingest/story-buffer threads not included) ingress={n_ingress} saved={n_saved}"
    )

    payload = {
        "articles": [_public_article(r) for r in page_rows],
        "top_stories": [_public_article(r) for r in top_stories],
    }
    _schedule_story_buffer_prewarm(story_cursor, total)

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Total-Count": str(total)},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
