"""
page_summaries.py — Deterministic summaries for rows passed in (e.g. one feed page).

- Skips articles with summary_status == 'ready' (unless forced elsewhere).
- Fills 'pending' rows using RSS excerpt + title rules (no AI).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from database import update_article_summary_fields
from services.deterministic_summary import deterministic_summary_for_article
from services.summarize import summarize_title_with_source


def fill_pending_summaries(
    rows: List[Dict],
    max_count: Optional[int] = None,
    persist_summary: Optional[Callable[[int, str, str], None]] = None,
) -> Tuple[int, int]:
    """
    For each row with summary_status == 'pending', compute deterministic summary and persist.

    Returns (count_set_to_ready, count_failed) — failed is always 0 unless DB error.
    """
    persist = persist_summary or update_article_summary_fields
    ready_n = 0
    failed_n = 0
    attempts = 0
    for row in rows:
        if max_count is not None and attempts >= max_count:
            break
        status = (row.get("summary_status") or "pending").strip().lower()
        if status == "ready":
            continue
        if status == "failed":
            continue

        aid = row.get("id")
        if aid is None:
            continue

        attempts += 1
        title = row.get("title") or ""
        excerpt = (row.get("rss_excerpt") or "").strip() or None
        link = (row.get("link") or "").strip() or None
        source = (row.get("source") or "").strip() or None

        try:
            text, src = summarize_title_with_source(
                title,
                article_text=excerpt,
                article_link=link,
                source=source,
            )
            print(f"[page_summaries] id={aid} summary_source={src}")
            persist(int(aid), summary=text, summary_status="ready")
            row["summary"] = text
            row["summary_status"] = "ready"
            ready_n += 1
        except Exception as e:
            fb, src = deterministic_summary_for_article(title, None)
            print(f"[page_summaries] id={aid} summary_source={src} error={e!r}")
            persist(int(aid), summary=fb, summary_status="ready")
            row["summary"] = fb
            row["summary_status"] = "ready"
            ready_n += 1

        row["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    return ready_n, failed_n
