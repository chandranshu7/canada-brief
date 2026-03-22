"""
ranking.py — rank_score for feed order (higher = earlier on page 1).

FORMULA (all components ≥ 0, summed into rank_score):
  rank_score = recency + coverage + diversity + image + category

  • recency — Exponential decay from publish time (hours). Very new stories get up to
    ~RECENCY_MAX points; older stories stay in the mix but fade, so a big breaking
    cluster can still beat a slightly newer thin item.

  • coverage — From trending_score (= articles merged in the cluster). Heavily covered
    stories get a strong lift (capped) so “everyone is reporting this” rises.

  • diversity — Distinct outlet names in `sources[]`. More sources → higher (capped).

  • image — Fixed bonus when `image_url` is set (richer cards / editorial feel).

  • category — Extra points when `category` matches important topics (politics,
    canada, world, business); only the single best matching boost applies (no stacking).

SQLite already orders by rank_score DESC, id DESC — no query change needed.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

# --- Tunable weights (keep formula readable) ---------------------------------
_RECENCY_MAX = 44.0
_RECENCY_HALF_LIFE_H = 30.0  # hours; ~half weight after this age

_COVERAGE_MULT = 3.2
_COVERAGE_CAP = 14  # max cluster size that still gains linearly (then flat)

_DIVERSITY_MULT = 4.5
_DIVERSITY_CAP = 9  # max distinct sources counted

_IMAGE_POINTS = 11.0

# Single best category match (substring, lowercased)
_CATEGORY_BOOSTS = (
    ("politics", 18.0),
    ("world", 15.0),
    ("canada", 13.0),
    ("business", 11.0),
)


def _parse_published_for_rank(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()

    try:
        dt = parsedate_to_datetime(text)
        if dt is not None:
            return dt
    except (TypeError, ValueError):
        pass

    if text.endswith("Z") or "T" in text[:32]:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass

    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%b %d, %Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:40], fmt)
        except ValueError:
            continue
    return None


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def compute_rank_breakdown(row: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Return (total_score, component dict) for logging and inspection.
    """
    trending = max(1, int(row.get("trending_score") or 1))
    sources = row.get("sources") or []
    n_sources = len(sources) if isinstance(sources, list) else 0
    n_sources = max(1, n_sources)  # at least primary source

    # Coverage: cluster size (heavily covered stories rank up)
    eff_trend = min(trending, _COVERAGE_CAP)
    coverage = eff_trend * _COVERAGE_MULT

    # Diversity: distinct outlets (capped)
    eff_div = min(n_sources, _DIVERSITY_CAP)
    diversity = eff_div * _DIVERSITY_MULT

    # Image
    has_image = 1.0 if (row.get("image_url") or "").strip() else 0.0
    image = has_image * _IMAGE_POINTS

    # Recency
    dt = _parse_published_for_rank(row.get("published"))
    if dt is not None:
        dt = _utc_naive(dt)
        now = datetime.utcnow()
        age_h = max(0.0, (now - dt).total_seconds() / 3600.0)
        recency = _RECENCY_MAX * math.exp(-age_h / _RECENCY_HALF_LIFE_H)
    else:
        recency = 9.0

    # Category: one boost only (strongest match)
    cat_raw = (row.get("category") or "").lower()
    category = 0.0
    for needle, pts in _CATEGORY_BOOSTS:
        if needle in cat_raw:
            category = max(category, pts)

    parts = {
        "recency": round(recency, 2),
        "coverage": round(coverage, 2),
        "diversity": round(diversity, 2),
        "image": round(image, 2),
        "category": round(category, 2),
    }
    total = sum(parts.values())
    return total, parts


def compute_rank_score(row: Dict[str, Any]) -> float:
    total, _ = compute_rank_breakdown(row)
    return round(total, 4)


def log_rank_debug_top(rows: List[Dict[str, Any]], limit: int = 10) -> None:
    """After ingest: print top `limit` stories by rank and strongest signal each."""
    if not rows:
        return
    enriched: List[Tuple[float, Dict[str, Any], Dict[str, float]]] = []
    for r in rows:
        total, parts = compute_rank_breakdown(r)
        enriched.append((total, r, parts))
    enriched.sort(key=lambda x: -x[0])

    print(f"[rank] debug top {min(limit, len(enriched))} by rank_score (formula in ranking.py docstring)")
    for i, (total, r, parts) in enumerate(enriched[:limit], start=1):
        title = (r.get("title") or "")[:72]
        strongest = max(parts.items(), key=lambda kv: kv[1])
        print(
            f"[rank]  #{i} score={total:.2f} strongest={strongest[0]}={strongest[1]:.2f} "
            f"parts={parts} title={title!r}"
        )
