"""
Stable, order-preserving deduplication for feed rows.

Keys (first occurrence wins, order preserved):
  1. Normalized link when `link` is non-empty (matches trailing-slash / case variants).
  2. Else: lowercased source + normalized title + lowercased published string.

Separate from ingest-time dedupe: protects /news from duplicate DB rows or merge gaps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from services.fetch_news import (
    content_fingerprint_for_dedup,
    normalize_link,
)


def article_dedupe_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    link = (row.get("link") or "").strip()
    if link:
        return ("link", normalize_link(link))
    return ("fp", content_fingerprint_for_dedup(row))


def dedupe_articles_stable(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """
    Return (deduped_rows, removed_count, sample_removed_key_reprs) — order preserved.
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []
    removed_reprs: List[str] = []
    for r in rows:
        k = article_dedupe_key(r)
        if k in seen:
            if len(removed_reprs) < 24:
                removed_reprs.append(repr(k))
            continue
        seen.add(k)
        out.append(r)
    removed = len(rows) - len(out)
    return out, removed, removed_reprs
