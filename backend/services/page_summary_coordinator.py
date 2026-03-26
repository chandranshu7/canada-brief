"""
Per-page summarization coordination: one in-flight LLM batch per API page (1-based).

- GET /news request path may poll briefly after scheduling page-level background work.
- Story-buffer prewarm uses a separate single-flight lock so it never races page work.
"""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional, Tuple

from database import (
    get_articles_page,
    load_local_feed_sorted,
    search_news_local_page,
    search_news_page,
)

_coord_lock = threading.Lock()
_in_flight_pages: set[int] = set()

# One background story-buffer prewarm at a time (avoids duplicate LLM batches).
_story_buffer_lock = threading.Lock()
_in_flight_story_buffer = False

# After the request thread schedules background summarization, poll DB this long for readiness.
REQUEST_POLL_WAIT_SECONDS = float(os.environ.get("PAGE_SUMMARY_REQUEST_POLL_S", "0.15"))
POLL_INTERVAL_S = float(os.environ.get("PAGE_SUMMARY_POLL_INTERVAL_S", "0.05"))


def _count_pending(rows: List[dict]) -> int:
    n = 0
    for r in rows:
        if (r.get("summary_status") or "pending").strip().lower() == "pending":
            n += 1
    return n


def try_acquire_page_summarize(page: int) -> bool:
    """Return True if this caller owns page summarization; False if already in-flight."""
    with _coord_lock:
        if page in _in_flight_pages:
            return False
        _in_flight_pages.add(page)
        return True


def release_page_summarize(page: int) -> None:
    with _coord_lock:
        _in_flight_pages.discard(page)


def try_acquire_story_buffer_prewarm() -> bool:
    """Return True if this worker may run story-buffer prewarm; False if already in flight."""
    global _in_flight_story_buffer
    with _story_buffer_lock:
        if _in_flight_story_buffer:
            return False
        _in_flight_story_buffer = True
        return True


def release_story_buffer_prewarm() -> None:
    global _in_flight_story_buffer
    with _story_buffer_lock:
        _in_flight_story_buffer = False


def _page_rows_for_mode(
    offset: int,
    limit: int,
    mode: str,
    city: Optional[str],
    province: Optional[str],
    search_q: Optional[str] = None,
) -> List[dict]:
    sq = (search_q or "").strip()
    if sq:
        if (mode or "").strip().lower() == "local" and (city or "").strip() and (
            province or ""
        ).strip():
            return search_news_local_page(
                offset, limit, city.strip(), province.strip(), sq
            )
        return search_news_page(offset, limit, sq)
    if (mode or "").strip().lower() == "local" and (city or "").strip() and (
        province or ""
    ).strip():
        full = load_local_feed_sorted(city.strip(), province.strip())
        return full[offset : offset + limit]
    return get_articles_page(offset, limit)


def get_page_rows_for_summarize(
    offset: int,
    limit: int,
    mode: str,
    city: Optional[str],
    province: Optional[str],
    search_q: Optional[str] = None,
) -> List[dict]:
    """Same row slice as GET /news uses for this page (feed or search)."""
    return _page_rows_for_mode(offset, limit, mode, city, province, search_q)


def short_wait_for_page_summaries_ready(
    page: int,
    page_size: int,
    *,
    mode: str = "general",
    city: Optional[str] = None,
    province: Optional[str] = None,
    search_q: Optional[str] = None,
) -> Tuple[List[dict], bool]:
    """
    Poll DB until no pending summaries on this page or REQUEST_POLL_WAIT_SECONDS elapses.

    Returns (rows_from_db, wait_succeeded).
    """
    offset = max(0, (page - 1) * page_size)
    deadline = time.monotonic() + REQUEST_POLL_WAIT_SECONDS
    last_rows: List[dict] = []

    while time.monotonic() < deadline:
        last_rows = _page_rows_for_mode(
            offset, page_size, mode, city, province, search_q
        )
        if _count_pending(last_rows) == 0:
            return last_rows, True
        time.sleep(POLL_INTERVAL_S)

    last_rows = _page_rows_for_mode(offset, page_size, mode, city, province, search_q)
    return last_rows, _count_pending(last_rows) == 0
