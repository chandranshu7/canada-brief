"""
ranking.py — simple ordering score for “what shows on page 1”.

Higher rank_score = earlier in the feed.

We blend (keep it simple):
- trending_score: cluster size (more articles merged → more coverage → higher)
- source count: distinct outlets in the cluster (diversity / importance proxy)
- image: small boost if we have a lead image (richer cards)
- recency: parse `published` string when possible; newer stories get a boost
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _parse_published_for_rank(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%b %d, %Y %H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:32], fmt)
        except ValueError:
            continue
    return None


def compute_rank_score(row: Dict[str, Any]) -> float:
    trending = float(row.get("trending_score") or 1)
    sources = row.get("sources") or []
    n_sources = len(sources) if isinstance(sources, list) else 0
    has_image = 1.0 if (row.get("image_url") or "").strip() else 0.0

    diversity = min(n_sources, 6) * 4.0
    coverage = trending * 32.0
    image_bonus = has_image * 10.0

    dt = _parse_published_for_rank(row.get("published"))
    if dt is not None:
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.utcnow()
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        recency = max(0.0, 9.0 - age_days * 1.2)
    else:
        recency = 3.0

    return coverage + diversity + image_bonus + recency
