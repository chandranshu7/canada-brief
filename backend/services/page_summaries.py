"""
page_summaries.py — lazy AI (or local) summaries only for the current page.

Reads rows from SQLite with summary_status == "pending", calls summarize_title once per row,
writes back summary + status. Never raises to the HTTP layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from database import update_article_summary_fields
from services.summarize import quick_fallback_summary, summarize_title


def fill_pending_summaries(rows: List[Dict]) -> int:
    """
    For each row still marked pending, generate a summary and persist it.

    Returns how many rows were updated on this request.
    """
    done = 0
    for row in rows:
        status = (row.get("summary_status") or "pending").strip().lower()
        # Cached summaries (ready) or permanent fallback (failed) are not regenerated.
        if status in ("ready", "failed"):
            continue

        aid = row.get("id")
        if aid is None:
            continue

        title = row.get("title") or ""
        excerpt = (row.get("rss_excerpt") or "").strip() or None

        try:
            text = summarize_title(title, article_text=excerpt)
            update_article_summary_fields(
                int(aid), summary=text, summary_status="ready"
            )
            row["summary"] = text
            row["summary_status"] = "ready"
            done += 1
        except Exception as e:
            fb = quick_fallback_summary(title)
            update_article_summary_fields(
                int(aid), summary=fb, summary_status="failed"
            )
            row["summary"] = fb
            row["summary_status"] = "failed"
            print(f"[page_summaries] id={aid} summarize error={e}; stored fallback")

        row["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    return done
