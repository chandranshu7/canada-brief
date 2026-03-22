"""
Per-page summarization coordination: one in-flight LLM batch per API page (1-based).

- Background prewarm and GET /news must not summarize the same page concurrently.
- Request path may poll briefly after scheduling background work (no synchronous LLM).
"""

from __future__ import annotations

import os
import threading
import time
from typing import List, Tuple

from database import get_articles_page

_coord_lock = threading.Lock()
_in_flight_pages: set[int] = set()

# After the request thread schedules background summarization, poll DB this long for readiness.
REQUEST_POLL_WAIT_SECONDS = float(os.environ.get("PAGE_SUMMARY_REQUEST_POLL_S", "0.5"))
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


def short_wait_for_page_summaries_ready(
    page: int, page_size: int
) -> Tuple[List[dict], bool]:
    """
    Poll DB until no pending summaries on this page or REQUEST_POLL_WAIT_SECONDS elapses.

    Returns (rows_from_db, wait_succeeded).
    """
    offset = max(0, (page - 1) * page_size)
    deadline = time.monotonic() + REQUEST_POLL_WAIT_SECONDS
    last_rows: List[dict] = []

    while time.monotonic() < deadline:
        last_rows = get_articles_page(offset, page_size)
        if _count_pending(last_rows) == 0:
            return last_rows, True
        time.sleep(POLL_INTERVAL_S)

    last_rows = get_articles_page(offset, page_size)
    return last_rows, _count_pending(last_rows) == 0
