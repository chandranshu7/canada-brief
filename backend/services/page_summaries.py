"""
page_summaries.py — LLM summaries only for rows you pass in (e.g. one feed page).

- Skips articles with summary_status == "ready" (cached; never regenerated).
- Skips "failed" (permanent fallback stored; avoids retry loops on every request).
- Processes "pending" rows: calls summarize_title, saves to DB, sets ready or failed.
- Never raises to the HTTP layer — one bad article does not fail the whole batch.

Optional max_count limits how many pending rows to process in one call (None = all).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database import update_article_summary_fields
from services.summarize import quick_fallback_summary, summarize_title


def fill_pending_summaries(
    rows: List[Dict], max_count: Optional[int] = None
) -> Tuple[int, int]:
    """
    For each row with summary_status == "pending", generate a summary and persist it.

    Returns (count_set_to_ready, count_set_to_failed).
    """
    ready_n = 0
    failed_n = 0
    attempts = 0
    for row in rows:
        if max_count is not None and attempts >= max_count:
            break
        status = (row.get("summary_status") or "pending").strip().lower()
        # Cached LLM summary — reuse forever for this row.
        if status == "ready":
            continue
        # Stored fallback after a real failure — do not retry every request.
        if status == "failed":
            continue

        aid = row.get("id")
        if aid is None:
            continue

        attempts += 1
        title = row.get("title") or ""
        excerpt = (row.get("rss_excerpt") or "").strip() or None

        try:
            text = summarize_title(title, article_text=excerpt)
            update_article_summary_fields(
                int(aid), summary=text, summary_status="ready"
            )
            row["summary"] = text
            row["summary_status"] = "ready"
            ready_n += 1
        except Exception as e:
            fb = quick_fallback_summary(title)
            update_article_summary_fields(
                int(aid), summary=fb, summary_status="failed"
            )
            row["summary"] = fb
            row["summary_status"] = "failed"
            failed_n += 1
            print(f"[page_summaries] id={aid} summarize error={e}; stored fallback")

        row["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    return ready_n, failed_n
