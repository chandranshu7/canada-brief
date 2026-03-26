"""
main.py - FastAPI entry point for the Canadian News App
Exposes GET /news (summarized feed) and GET /daily-brief (top 5 daily snapshot).
"""

import asyncio
import hashlib
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load backend/.env before other imports (DATABASE_URL, OPENAI_API_KEY, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from env import get_openai_api_key
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import (
    count_articles,
    count_local_articles,
    count_news_local_search,
    count_news_search,
    count_pending_articles,
    get_articles_page,
    get_articles_top,
    init_db,
    local_scope_max_last_updated,
    load_local_feed_sorted,
    merge_news_articles,
    save_local_news_items,
    save_news_items,
    search_news_local_page,
    search_news_page,
    update_local_article_summary_fields,
)
from services.canada_locations import location_meta_for_log
from services.local_source_config import build_local_feed_plan, local_coverage_from_plan
from services.local_feed import (
    log_curated_sources,
    log_local_feed_summary,
    log_local_pagination_debug,
)
from services.location_ranking import (
    log_location_rank_mix,
    log_top_ranked_with_location,
)
from services.fetch_news import (
    fetch_general_feeds,
    fetch_general_feeds_with_diagnostics,
    fetch_local_feeds,
)
from services.deterministic_summary import assign_deterministic_summary_to_row, clamp_summary_display
from services.page_summaries import fill_pending_summaries
from services.page_summary_coordinator import (
    REQUEST_POLL_WAIT_SECONDS,
    get_page_rows_for_summarize,
    release_page_summarize,
    release_story_buffer_prewarm,
    short_wait_for_page_summaries_ready,
    try_acquire_page_summarize,
    try_acquire_story_buffer_prewarm,
)
from services.ranking import compute_rank_score, log_rank_debug_top
from services.story_clustering import cluster_articles
from services.topic_classification import log_topic_classification_batch
from services.daily_brief import get_daily_brief_payload
from services.feed_dedupe import dedupe_articles_stable
from services.summarize import display_summary_for_response

PAGE_SIZE = 5
TOP_STORIES_LIMIT = 3
LOCAL_INGEST_MAX_AGE_SEC = int(os.environ.get("LOCAL_INGEST_MAX_AGE_SEC", "900"))


def _search_query_term(q: Optional[str], search: Optional[str]) -> str:
    """First non-empty `q` or `search` query param (trimmed)."""
    for v in (q, search):
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _parse_iso_utc(value: str) -> Optional[datetime]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _local_scope_is_stale(city: str, province: str) -> bool:
    """True when local scope has no rows or latest update is older than configured threshold."""
    if count_local_articles(city, province) == 0:
        return True
    last_iso = local_scope_max_last_updated(city, province)
    last_dt = _parse_iso_utc(last_iso or "")
    if last_dt is None:
        return True
    age_s = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return age_s >= max(60, LOCAL_INGEST_MAX_AGE_SEC)

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
    "topic_category",
    "region",
    "image_url",
    "video_url",
    "sources",
    "related_links",
    "cluster_id",
)

_RESPONSE_PLACEHOLDER_IMAGE_URLS = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=60",
)


def _placeholder_image_for_row(row: dict) -> str:
    title = (row.get("title") or "").lower()
    link = (row.get("link") or "").lower()
    src = (row.get("source") or "").lower()
    digest = hashlib.md5(f"{title}|{link}|{src}".encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(_RESPONSE_PLACEHOLDER_IMAGE_URLS)
    return _RESPONSE_PLACEHOLDER_IMAGE_URLS[idx]


def _ensure_unique_images(rows: list[dict], label: str) -> None:
    """Mutates rows in-place so repeated image URLs on the same response are replaced."""
    seen: set[str] = set()
    replaced = 0

    def _image_key(url: str) -> str:
        raw = (url or "").strip().lower()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
            host = (p.netloc or "").lower()
            path = (p.path or "").lower().rstrip("/")
            if host and path:
                return f"{host}{path}"
        except Exception:
            pass
        return raw

    for row in rows:
        raw = (row.get("image_url") or "").strip()
        if not raw:
            row["image_url"] = _placeholder_image_for_row(row)
            replaced += 1
            continue
        key = _image_key(raw)
        if key in seen:
            row["image_url"] = _placeholder_image_for_row(row)
            replaced += 1
            continue
        seen.add(key)
    if replaced > 0:
        print(f"[/news] image_dedupe label={label} replaced={replaced}")


def _public_article(row: dict) -> dict:
    """Public JSON shape; summary always length-normalized (legacy DB rows included)."""
    d = {k: row.get(k) for k in _ARTICLE_PUBLIC_KEYS}
    if isinstance(d.get("summary"), str):
        d["summary"] = clamp_summary_display(d["summary"] or "")
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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Background general ingest (merge-by-link); does not replace full refresh via /news?refresh=true.
_last_ingest_completed_at: Optional[str] = None
_background_ingest_lock = threading.Lock()
# Background merge ingest: every ~2.5 minutes for fresher Canada Brief (env override).
INGEST_INTERVAL_SEC = int(os.environ.get("INGEST_INTERVAL_SEC", "150"))


def _run_background_general_merge() -> Dict[str, Any]:
    """
    Reuses fetch_general_feeds → cluster → rank → deterministic summary, then merge_news_articles
    (insert only new normalized links). Does not clear `news` — safe for periodic runs.
    """
    global _last_ingest_completed_at
    with _background_ingest_lock:
        t_merge = time.time()
        try:
            raw_items, fetch_diag = fetch_general_feeds_with_diagnostics()
            clustered = cluster_articles(raw_items)
            now = datetime.now(timezone.utc).isoformat()
            prefer_ai = bool(get_openai_api_key())
            for row in clustered:
                ex = row.get("rss_excerpt") or ""
                row["rss_excerpt"] = str(ex)[:12000]
                assign_deterministic_summary_to_row(row)
                if prefer_ai:
                    row["summary_status"] = "pending"
                row["rank_score"] = compute_rank_score(row)
                row["last_updated_at"] = now
            log_rank_debug_top(clustered, limit=10)
            log_topic_classification_batch(
                clustered, log_prefix="general", stage="post_cluster"
            )
            inserted, merge_diag = merge_news_articles(clustered)
        except Exception as e:
            print(f"[ingest] background_merge failed (non-fatal): {e}")
            return {
                "ok": False,
                "error": str(e)[:500],
                "inserted": 0,
            }
        _last_ingest_completed_at = datetime.now(timezone.utc).isoformat()
        merge_elapsed = time.time() - t_merge

        pipeline_skip = (
            fetch_diag.get("pipeline_skipped_duplicate_link", 0)
            + fetch_diag.get("pipeline_skipped_duplicate_content_hash", 0)
        )
        merge_skip = (
            merge_diag.get("merge_skipped_missing_link", 0)
            + merge_diag.get("merge_skipped_duplicate_db_link", 0)
            + merge_diag.get("merge_skipped_duplicate_batch_link", 0)
            + merge_diag.get("merge_skipped_duplicate_db_content_hash", 0)
            + merge_diag.get("merge_skipped_duplicate_batch_content_hash", 0)
            + merge_diag.get("merge_skipped_integrity_error", 0)
        )
        skipped_duplicates = pipeline_skip + merge_skip

        out: Dict[str, Any] = {
            "ok": True,
            "inserted": inserted,
            "last_ingested_at": _last_ingest_completed_at,
            "feeds_requested": fetch_diag.get("feeds_requested"),
            "feeds_fetched": fetch_diag.get("feeds_fetched")
            or fetch_diag.get("feeds_fetched_ok"),
            "feeds_fetch_failed": fetch_diag.get("feeds_fetch_failed"),
            "failed_feed_samples": fetch_diag.get("failed_feed_samples"),
            "raw_entries": fetch_diag.get("raw_entries"),
            "candidates": fetch_diag.get("candidates"),
            "clustered": len(clustered),
            "pipeline_skipped_duplicate_link": fetch_diag.get(
                "pipeline_skipped_duplicate_link"
            ),
            "pipeline_skipped_duplicate_content_hash": fetch_diag.get(
                "pipeline_skipped_duplicate_content_hash"
            ),
            "skipped_duplicates": skipped_duplicates,
            "skipped_duplicates_pipeline": pipeline_skip,
            "merge_skipped_missing_link": merge_diag.get("merge_skipped_missing_link"),
            "merge_skipped_duplicate_db_link": merge_diag.get(
                "merge_skipped_duplicate_db_link"
            ),
            "merge_skipped_duplicate_batch_link": merge_diag.get(
                "merge_skipped_duplicate_batch_link"
            ),
            "merge_skipped_duplicate_db_content_hash": merge_diag.get(
                "merge_skipped_duplicate_db_content_hash"
            ),
            "merge_skipped_duplicate_batch_content_hash": merge_diag.get(
                "merge_skipped_duplicate_batch_content_hash"
            ),
            "skipped_duplicates_merge": merge_skip,
            "skipped_duplicates_total": skipped_duplicates,
            "ingestion_time_seconds": fetch_diag.get("ingestion_time_seconds"),
            "merge_wall_time_seconds": round(merge_elapsed, 4),
            "sample_pipeline_skipped_links": fetch_diag.get("sample_pipeline_skipped_links"),
            "sample_pipeline_skipped_content_hash": fetch_diag.get(
                "sample_pipeline_skipped_content_hash"
            ),
            "sample_merge_skipped": merge_diag.get("sample_skipped_duplicates"),
            "sample_new_links_inserted": merge_diag.get("sample_new_links"),
            "after_canadian_filter": fetch_diag.get("after_canadian_filter"),
            "filtered_non_canadian": fetch_diag.get("filtered_non_canadian"),
        }
        print(
            f"[ingest] summary feeds_requested={out['feeds_requested']} "
            f"feeds_fetched={out['feeds_fetched']} raw_entries={out['raw_entries']} "
            f"candidates={out['candidates']} skipped_duplicates={skipped_duplicates} "
            f"inserted={inserted} ingestion_time_seconds={out['ingestion_time_seconds']} "
            f"merge_wall_time_seconds={out['merge_wall_time_seconds']}"
        )
        print(
            f"[ingest] background_merge last_ingested_at={_last_ingest_completed_at} "
            f"raw_entries={out['raw_entries']} candidates={out['candidates']} "
            f"clustered={out['clustered']} inserted={inserted} "
            f"skipped_pipeline={pipeline_skip} skipped_merge={merge_skip}"
        )
        if inserted > 0:
            _schedule_prewarm_after_ingest()
        return out


async def _background_ingest_loop() -> None:
    print("[ingest] started")
    await asyncio.sleep(3)
    while True:
        try:
            print("[ingest] fetching feeds")
            t0 = time.time()
            if hasattr(asyncio, "to_thread"):
                result = await asyncio.to_thread(_run_background_general_merge)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, _run_background_general_merge
                )
            elapsed = time.time() - t0
            inserted = result.get("inserted", 0)
            print(f"[ingest] new articles inserted: {inserted}")
            print(f"[ingest] completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[ingest] error: {e}")
        await asyncio.sleep(INGEST_INTERVAL_SEC)


@app.on_event("startup")
async def startup():
    _log_startup_config()
    init_db()
    asyncio.create_task(_background_ingest_loop())


def _strip_rss_excerpt(row: dict) -> None:
    row.pop("rss_excerpt", None)


def _log_story_summary(row: dict, display_source: str) -> None:
    """Structured log: DB status vs what the client sees (excerpt vs title fallback, etc.)."""
    aid = row.get("id")
    link = (row.get("link") or "")[:120]
    st = (row.get("summary_status") or "pending").strip().lower()
    print(
        f"[summary] story id={aid} summary_status={st} summary_source={display_source} link={link!r}"
    )


def _apply_summary_for_display(row: dict) -> None:
    """
    Set `summary` for JSON from stored text or deterministic RSS/title fallback.
    """
    ex = (row.get("rss_excerpt") or "").strip() or None
    st = (row.get("summary_status") or "pending").strip().lower()
    text, src = display_summary_for_response(
        title=row.get("title") or "",
        summary=row.get("summary"),
        rss_excerpt=ex,
        summary_status=st,
    )
    row["summary"] = text
    _log_story_summary(row, src)


def _count_pending(rows: list) -> int:
    n = 0
    for r in rows:
        if (r.get("summary_status") or "pending").strip().lower() == "pending":
            n += 1
    return n


def _row_pending_llm(row: dict) -> bool:
    """True if this row still needs a deterministic summary fill (legacy 'pending')."""
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


def _ingest_initial_story_buffer_local(city: str, province: str) -> tuple[int, int, int]:
    """First three Local-mode stories after a local ingest (news_local)."""
    rows = load_local_feed_sorted(city, province)[:3]
    pending = [r for r in rows if _row_pending_llm(r)]
    if not pending:
        return 0, 0, 0
    ready_n, failed_n = fill_pending_summaries(
        pending,
        max_count=None,
        persist_summary=update_local_article_summary_fields,
    )
    return ready_n, failed_n, 0


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
    """Fire-and-forget thread: fills any pending deterministic summaries after DB save."""
    t = threading.Thread(target=_background_prewarm_worker, daemon=True)
    t.start()
    print("[story_prewarm] ingest background task scheduled (non-blocking)")


def _background_prewarm_worker_local(city: str, province: str) -> None:
    """After local ingest: warm first 3 stories in `news_local`."""
    print(
        f"[story_prewarm] local ingest background started city={city!r} province={province!r}"
    )
    t0 = time.time()
    try:
        pr, pf, _ = _ingest_initial_story_buffer_local(city, province)
        elapsed = time.time() - t0
        print(
            f"[story_prewarm] local ingest background finished time_s={elapsed:.3f} "
            f"summaries_ready={pr} summaries_failed={pf}"
        )
    except Exception as e:
        print(f"[story_prewarm] local ingest background failed: {e}")


def _schedule_prewarm_after_local_ingest(city: str, province: str) -> None:
    t = threading.Thread(
        target=_background_prewarm_worker_local,
        args=(city, province),
        daemon=True,
    )
    t.start()
    print("[story_prewarm] local ingest background task scheduled (non-blocking)")


def _story_buffer_prewarm_worker(
    cursor: int,
    total_rows_hint: int,
    city: Optional[str] = None,
    province: Optional[str] = None,
    mode: str = "general",
) -> None:
    """
    Ensure the next STORY_BUFFER_AHEAD stories after `cursor` have summaries (ready or failed).
    Only fills pending rows; skips cached ready/failed. Single-flight via coordinator.
    """
    if not try_acquire_story_buffer_prewarm():
        print("[story_prewarm] skip reason=in_flight")
        return
    try:
        local_full: Optional[List[dict]] = None
        if mode == "local" and city and province:
            local_full = load_local_feed_sorted(city, province)
            total_rows = len(local_full)
        else:
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

        if mode == "local" and city and province and local_full is not None:
            if cursor + 1 >= len(local_full):
                print(
                    f"[story_prewarm] skip cursor={cursor} no_stories_ahead "
                    f"local_feed_len={len(local_full)}"
                )
                return
            ahead = local_full[cursor + 1 : cursor + 1 + STORY_BUFFER_AHEAD]
        else:
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

        persist = (
            update_local_article_summary_fields
            if mode == "local" and city and province
            else None
        )
        n_ready, n_failed = fill_pending_summaries(
            pending, max_count=len(pending), persist_summary=persist
        )
        print(
            f"[story_prewarm] done cursor={cursor} prewarmed_ready={n_ready} "
            f"prewarmed_failed={n_failed}"
        )
    except Exception as e:
        print(f"[story_prewarm] error: {e}")
    finally:
        release_story_buffer_prewarm()


def _schedule_story_buffer_prewarm(
    cursor: int,
    total_rows: int,
    city: Optional[str] = None,
    province: Optional[str] = None,
    mode: str = "general",
) -> None:
    """Fire-and-forget: fill next STORY_BUFFER_AHEAD stories after cursor (global feed index)."""
    t = threading.Thread(
        target=_story_buffer_prewarm_worker,
        args=(cursor, total_rows, city, province, mode),
        daemon=True,
    )
    t.start()


def _run_page_summaries_background(
    page: int,
    offset: int,
    page_size: int,
    mode: str = "general",
    city: Optional[str] = None,
    province: Optional[str] = None,
    search_q: Optional[str] = None,
) -> None:
    """Deterministic summary fill for one page; always releases the page lock."""
    try:
        rows = get_page_rows_for_summarize(
            offset, page_size, mode, city, province, search_q
        )
        if (mode or "").strip().lower() == "local" and (city or "").strip() and (
            province or ""
        ).strip():
            persist = update_local_article_summary_fields
        else:
            persist = None
        n_ready, n_failed = fill_pending_summaries(
            rows, max_count=None, persist_summary=persist
        )
        print(
            f"[page_summarize] background finished page={page} "
            f"summaries_ready={n_ready} summaries_failed={n_failed}"
        )
    except Exception as e:
        print(f"[page_summarize] background page={page} error: {e}")
    finally:
        release_page_summarize(page)


def _run_ingest_general() -> tuple[int, int, int, float]:
    """
    General refresh: national RSS only → cluster → rank → `news` table.
    """
    t0 = time.time()
    raw_items = fetch_general_feeds()
    n_ingress = len(raw_items)
    clustered = cluster_articles(raw_items)
    n_cluster = len(clustered)
    now = datetime.now(timezone.utc).isoformat()
    prefer_ai = bool(get_openai_api_key())
    for row in clustered:
        ex = row.get("rss_excerpt") or ""
        row["rss_excerpt"] = str(ex)[:12000]
        assign_deterministic_summary_to_row(row)
        if prefer_ai:
            row["summary_status"] = "pending"
        row["rank_score"] = compute_rank_score(row)
        row["last_updated_at"] = now
    log_rank_debug_top(clustered, limit=10)
    log_topic_classification_batch(clustered, log_prefix="general", stage="post_cluster")
    save_news_items(clustered)

    ingest_elapsed = time.time() - t0
    print(
        f"[ingest] general_ingest_complete (fetch+cluster+rank+save) time_s={ingest_elapsed:.3f} "
        f"(deterministic summaries; background prewarm optional)"
    )
    _schedule_prewarm_after_ingest()
    print(
        f"[/news] general ingest done: ingress_to_cluster={n_ingress} "
        f"clusters_saved={n_cluster} ingest_path_s={time.time() - t0:.3f}"
    )
    return n_ingress, n_cluster, n_cluster, ingest_elapsed


def _run_ingest_local(city: str, province: str) -> tuple[int, int, int, float]:
    """
    Local refresh: city/province/national feeds for one location only → `news_local`.
    """
    t0 = time.time()
    raw_items = fetch_local_feeds(city, province)
    n_ingress = len(raw_items)
    clustered = cluster_articles(raw_items)
    n_cluster = len(clustered)
    now = datetime.now(timezone.utc).isoformat()
    prefer_ai = bool(get_openai_api_key())
    for row in clustered:
        ex = row.get("rss_excerpt") or ""
        row["rss_excerpt"] = str(ex)[:12000]
        assign_deterministic_summary_to_row(row)
        if prefer_ai:
            row["summary_status"] = "pending"
        row["rank_score"] = compute_rank_score(row)
        row["last_updated_at"] = now
    log_rank_debug_top(clustered, limit=10)
    log_topic_classification_batch(clustered, log_prefix="local", stage="post_cluster")
    save_local_news_items(clustered, city, province)

    ingest_elapsed = time.time() - t0
    print(
        f"[ingest] local_ingest_complete city={city!r} province={province!r} "
        f"time_s={ingest_elapsed:.3f}"
    )
    _schedule_prewarm_after_local_ingest(city, province)
    print(
        f"[/news] local ingest done: ingress_to_cluster={n_ingress} "
        f"clusters_saved={n_cluster} ingest_path_s={time.time() - t0:.3f}"
    )
    return n_ingress, n_cluster, n_cluster, ingest_elapsed


@app.get("/news")
def get_news(
    refresh: bool = False,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    cursor: Optional[int] = None,
    mode: str = Query(
        "general",
        description="general = Canada-wide feed; local = city-first + regional sources",
    ),
    city: Optional[str] = Query(None, description="City for Local mode"),
    province: Optional[str] = Query(
        None, description="Province/territory for Local mode",
    ),
    province_code: Optional[str] = Query(
        None, description="Province code (e.g. ON) from client dataset",
    ),
    location_slug: Optional[str] = Query(
        None,
        alias="slug",
        description="Stable slug from Canada locations dataset (optional)",
    ),
    q: Optional[str] = Query(
        None,
        description="Search title, summary, region, source, category, excerpt (general or local DB)",
    ),
    search: Optional[str] = Query(
        None,
        description="Alias for q",
    ),
):
    """
    Paginated feed: JSON object with "articles" and optional "top_stories".

    General mode: `articles` is the deduped page slice only; `top_stories` is always empty
    (no separate top strip — avoids duplicate ids with page 1).

    Local mode (city+province): `top_stories` is always empty — same paginated-only pattern.

    After ingest/cold-start, page 1 may skip synchronous background fill.

    Request path does not call external AI. Background threads only run deterministic
    summary fill for any legacy pending rows.

    `cursor` is the 0-based global index of the current story in feed order (rank_score DESC).
    Defaults to the first story on this page: (page-1)*page_size. Used for story-buffer prewarm
    (next two stories ahead), not full-page prewarm.
    """
    t_start = time.time()
    page = max(1, int(page))
    page_size = min(PAGE_SIZE, max(1, int(page_size)))

    n_ingress = n_cluster = n_saved = 0
    ingest_elapsed_s = 0.0

    city_clean = (city or "").strip() or None
    province_clean = (province or "").strip() or None
    province_code_q = (province_code or "").strip() or None
    location_slug_q = (location_slug or "").strip() or None
    mode_clean = (mode or "general").strip().lower()
    if mode_clean not in ("general", "local"):
        mode_clean = "general"

    need_local = mode_clean == "local" and bool(city_clean and province_clean)
    local_feed_plan = None
    if need_local:
        ds_meta = location_meta_for_log(city_clean or "", province_clean or "")
        print(
            "[/news] local_selected_location "
            f"city={city_clean!r} province={province_clean!r} "
            f"client_province_code={province_code_q!r} client_slug={location_slug_q!r} "
            f"dataset_match={ds_meta}"
        )
        local_feed_plan = build_local_feed_plan(city_clean or "", province_clean or "")

    if refresh:
        if need_local:
            refresh_mode = "ingest_local"
            print("[/news] refresh mode ON — local ingest (scoped feeds only)")
            try:
                n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest_local(
                    city_clean or "",
                    province_clean or "",
                )
            except Exception as e:
                raise HTTPException(
                    status_code=502, detail=f"Local ingest failed: {e}"
                ) from e
        else:
            refresh_mode = "ingest_general"
            print("[/news] refresh mode ON — general ingest (national feeds)")
            try:
                n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest_general()
            except Exception as e:
                raise HTTPException(
                    status_code=502, detail=f"Ingest failed: {e}"
                ) from e
    elif need_local and _local_scope_is_stale(city_clean or "", province_clean or ""):
        refresh_mode = "stale_local"
        print(
            "[/news] local scope stale/empty — auto local ingest "
            f"(max_age_s={LOCAL_INGEST_MAX_AGE_SEC})"
        )
        try:
            n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest_local(
                city_clean or "",
                province_clean or "",
            )
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Local ingest failed: {e}"
            ) from e
    elif count_articles() == 0:
        refresh_mode = "cold_start_general"
        print("[/news] DB empty — cold-start general ingest")
        try:
            n_ingress, n_cluster, n_saved, ingest_elapsed_s = _run_ingest_general()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ingest failed: {e}") from e
    else:
        refresh_mode = "read"
        print("[/news] serving from database")

    offset = (page - 1) * page_size
    if cursor is None:
        story_cursor = offset
    else:
        story_cursor = max(0, int(cursor))

    t_read = time.time()
    sorted_full: Optional[List[dict]] = None
    local_paginated_ids: Optional[List[Optional[int]]] = None
    general_paginated_ids: Optional[List[Optional[int]]] = None
    search_q = _search_query_term(q, search)

    if search_q:
        print(
            f"[/news] feed_search mode={mode_clean!r} q={search_q!r} "
            f"page={page} offset={offset} limit={page_size}"
        )
        sorted_full = None
        if need_local:
            total = count_news_local_search(
                city_clean or "", province_clean or "", search_q
            )
            page_rows = search_news_local_page(
                offset,
                page_size,
                city_clean or "",
                province_clean or "",
                search_q,
            )
            top_stories = []
        elif mode_clean == "local":
            total = count_news_search(search_q)
            page_rows = search_news_page(offset, page_size, search_q)
            top_stories = []
        else:
            total = count_news_search(search_q)
            page_rows = search_news_page(offset, page_size, search_q)
            top_stories = []
        print(
            f"[/news] search_result total_matched={total} rows_returned={len(page_rows)} "
            f"ids={[r.get('id') for r in page_rows]}"
        )
    elif mode_clean == "local" and city_clean and province_clean:
        print(
            f"[/news] feed_mode=local city={city_clean!r} province={province_clean!r}"
        )
        sorted_full = load_local_feed_sorted(
            city_clean, province_clean, plan=local_feed_plan
        )
        total = len(sorted_full)
        log_curated_sources(city_clean)
        log_location_rank_mix(sorted_full, city_clean, province_clean)
        log_top_ranked_with_location(sorted_full, city_clean, province_clean)
        log_local_feed_summary(sorted_full, city_clean, province_clean)
        page_rows = sorted_full[offset : offset + page_size]
        # Local mode: do not attach a global "top 3" strip — it repeated the same ids on
        # every page (summary logs + JSON) and was not part of the paginated slice.
        top_stories = []
    elif mode_clean == "local":
        print(
            "[/news] feed_mode=local missing city/province — using general Canada-wide feed"
        )
        total = count_articles()
        page_rows = get_articles_page(offset, page_size)
        top_stories = get_articles_top(TOP_STORIES_LIMIT)
    else:
        print("[/news] feed_mode=general")
        total = count_articles()
        page_rows = get_articles_page(offset, page_size)
        # No global top-three strip: same ranked rows as pagination only (matches local mode).
        top_stories = []
    read_elapsed = time.time() - t_read

    print(
        f"[/news] db_page_query total_rows={total} offset={offset} limit={page_size} "
        f"rows_returned={len(page_rows)} max_allowed_page={_max_page_number(total, page_size)}"
    )

    pending_on_page = _count_pending(page_rows)
    page1_warm_before_lazy = page == 1 and pending_on_page == 0

    skip_lazy_fill = page == 1 and refresh_mode in (
        "ingest_general",
        "ingest_local",
        "cold_start_general",
        "cold_start_local",
    )

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
                args=(
                    page,
                    offset,
                    page_size,
                    mode_clean,
                    city_clean,
                    province_clean,
                    search_q or None,
                ),
                daemon=True,
            ).start()
            page_rows, wait_ok = short_wait_for_page_summaries_ready(
                page,
                page_size,
                mode=mode_clean,
                city=city_clean,
                province=province_clean,
                search_q=search_q or None,
            )
            if wait_ok:
                print(
                    f"[/news] page={page} request poll succeeded within "
                    f"{REQUEST_POLL_WAIT_SECONDS:.2f}s — returning DB summaries"
                )
            else:
                print(f"[request] fallback_used page={page} reason=timeout")
    lazy_elapsed = time.time() - t_lazy

    page_rows, dup_page_n, dup_page_keys = dedupe_articles_stable(page_rows)
    top_stories, dup_top_n, dup_top_keys = dedupe_articles_stable(top_stories)
    if dup_page_n or dup_top_n:
        print(
            f"[/news] feed_dedupe removed page_rows={dup_page_n} top_stories={dup_top_n} "
            f"sample_keys_page={dup_page_keys!r} sample_keys_top={dup_top_keys!r}"
        )

    _ensure_unique_images(page_rows, label=f"page:{page}")
    _ensure_unique_images(top_stories, label=f"top:{page}")

    if mode_clean == "general":
        general_paginated_ids = [r.get("id") for r in page_rows]
        print(
            "[/news] general_paginated_ids "
            f"page={page} ids={general_paginated_ids}"
        )

    n_page = len(page_rows)
    print(
        f"[/news] page_rows_final total_rows={total} offset={offset} limit={page_size} "
        f"rows_returned={n_page}"
    )

    if sorted_full is not None:
        local_paginated_ids = [r.get("id") for r in page_rows]
        log_local_pagination_debug(
            sorted_full,
            page,
            offset,
            page_size,
            page_rows,
            city_clean or "",
            province_clean or "",
        )

    for row in top_stories:
        _apply_summary_for_display(row)
        _strip_rss_excerpt(row)

    for row in page_rows:
        _apply_summary_for_display(row)
        _strip_rss_excerpt(row)

    if mode_clean == "general" and general_paginated_ids is not None:
        sent = [r.get("id") for r in page_rows]
        print(
            "[/news] general_ids_sent_to_summary_apply "
            f"page={page} ids={sent} (page_rows_final only; no top_stories)"
        )
        if sent != general_paginated_ids:
            print(
                "[/news] WARN general id drift after summary apply: "
                f"before={general_paginated_ids!r} after={sent!r}"
            )

    if sorted_full is not None and local_paginated_ids is not None:
        print(
            "[/news] local_ids_sent_to_summary_apply "
            f"page={page} ids={local_paginated_ids} "
            f"(top_stories strip skipped in local mode; only page rows)"
        )

    if search_q and need_local and city_clean and province_clean:
        print(
            "[/news] local_search_ids_sent_to_summary_apply "
            f"page={page} ids={[r.get('id') for r in page_rows]}"
        )

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
    if need_local and city_clean and province_clean and local_feed_plan is not None:
        payload["local_coverage"] = local_coverage_from_plan(local_feed_plan)
    if mode_clean == "general" and general_paginated_ids is not None:
        final_ids = [a.get("id") for a in payload["articles"]]
        print(f"[/news] general_final_response_ids page={page} ids={final_ids}")
        if final_ids != general_paginated_ids:
            print(
                "[/news] WARN general response id mismatch: "
                f"final_response_ids={final_ids} general_paginated_ids={general_paginated_ids}"
            )
    if sorted_full is not None and local_paginated_ids is not None:
        final_ids = [a.get("id") for a in payload["articles"]]
        print(f"[/news] local_final_response_ids page={page} ids={final_ids}")
        if final_ids != local_paginated_ids:
            print(
                "[/news] WARN local response id mismatch: "
                f"final_response_ids={final_ids} paginated_ids_this_page={local_paginated_ids}"
            )
    if search_q and need_local and city_clean and province_clean:
        print(
            "[/news] local_search_final_response_ids "
            f"page={page} ids={[a.get('id') for a in payload['articles']]}"
        )

    _schedule_story_buffer_prewarm(
        story_cursor, total, city_clean, province_clean, mode_clean
    )

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Total-Count": str(total)},
    )


@app.get("/daily-brief")
def daily_brief():
    """
    Top 5 Canada-wide stories: same rank + dedupe as general /news, re-ranked to prefer
    same-day (UTC) items. Refreshed on a short TTL and whenever new rows are inserted (max id).
    """
    payload = get_daily_brief_payload()
    return JSONResponse(content=jsonable_encoder(payload))


@app.post("/ingest/run")
def ingest_run():
    """
    Manual trigger: same merge ingest as the background loop (insert new links only).
    For testing / ops — does not replace GET /news?refresh=true full refresh.
    """
    try:
        payload = _run_background_general_merge()
        return JSONResponse(content=jsonable_encoder(payload))
    except Exception as e:
        print(f"[ingest] manual run error: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)},
        )


@app.get("/health")
def health():
    return {"status": "ok"}
