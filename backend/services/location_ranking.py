"""
location_ranking.py — Per-request ordering on top of stored rank_score.

When the user picks a city/province, we add a location boost so:
  local (city match) > province match > Canada-wide > baseline

Does not change stored rank_score; only affects read-time ordering.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Boosts (additive to rank_score). Tune relative to ranking.compute_rank_breakdown totals.
_CITY_BOOST = 92.0
_PROVINCE_BOOST = 50.0
_NATIONAL_BOOST = 24.0

# Map article `region` labels (city or province) to province name for matching.
CITY_TO_PROVINCE: Dict[str, str] = {
    "Ottawa": "Ontario",
    "Toronto": "Ontario",
    "Montreal": "Quebec",
    "Vancouver": "British Columbia",
    "Calgary": "Alberta",
    "Edmonton": "Alberta",
    "Winnipeg": "Manitoba",
    "Halifax": "Nova Scotia",
    "Regina": "Saskatchewan",
    "Saskatoon": "Saskatchewan",
}

# Exposed for local_feed strict tiering (same labels as infer_region / article regions).
PROVINCE_NAMES = frozenset(
    {
        "Ontario",
        "Quebec",
        "Alberta",
        "British Columbia",
        "Manitoba",
        "Saskatchewan",
        "Nova Scotia",
        "New Brunswick",
        "Prince Edward Island",
        "Newfoundland and Labrador",
        "Yukon",
        "Northwest Territories",
        "Nunavut",
    }
)


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def article_province_for_region(region: str) -> Optional[str]:
    """Province name for this article's region label, if known."""
    r = _norm(region)
    if not r:
        return None
    if r in PROVINCE_NAMES:
        return r
    return CITY_TO_PROVINCE.get(r)


def location_boost_and_reason(
    region: Optional[str],
    user_city: Optional[str],
    user_province: Optional[str],
) -> Tuple[float, str]:
    """
    Return (boost, reason) for logging. No preference → (0, no_preference).
    """
    uc = _norm(user_city) or None
    up = _norm(user_province) or None
    if not uc and not up:
        return 0.0, "no_preference"

    r = _norm(region)
    if not r:
        return 0.0, "empty_region"

    if uc and r.lower() == uc.lower():
        return _CITY_BOOST, "city_exact"

    if up:
        ul = up.lower()
        if r.lower() == ul:
            return _PROVINCE_BOOST, "province_exact"
        ap = article_province_for_region(r)
        if ap and ap.lower() == ul:
            return _PROVINCE_BOOST, "province_via_city"

    if r == "Canada" and (uc or up):
        return _NATIONAL_BOOST, "national"

    return 0.0, "baseline"


def effective_rank(article: Dict, user_city: Optional[str], user_province: Optional[str]) -> float:
    base = float(article.get("rank_score") or 0.0)
    boost, _ = location_boost_and_reason(article.get("region"), user_city, user_province)
    return base + boost


def sort_articles_by_location_and_rank(
    articles: List[Dict],
    user_city: Optional[str],
    user_province: Optional[str],
) -> List[Dict]:
    """Stable sort: higher effective rank first, then higher id."""
    uc = _norm(user_city) or None
    up = _norm(user_province) or None

    def key(a: Dict) -> Tuple[float, int]:
        aid = int(a.get("id") or 0)
        return (-effective_rank(a, uc, up), -aid)

    out = list(articles)
    out.sort(key=key)
    return out


def classify_bucket(
    region: Optional[str],
    user_city: Optional[str],
    user_province: Optional[str],
) -> str:
    """Rough bucket for logging counts."""
    uc = _norm(user_city) or None
    up = _norm(user_province) or None
    if not uc and not up:
        return "no_preference"
    _, reason = location_boost_and_reason(region, uc, up)
    if reason == "city_exact":
        return "local"
    if reason in ("province_exact", "province_via_city"):
        return "province"
    if reason == "national":
        return "national"
    return "other"


def log_location_rank_mix(
    sorted_articles: List[Dict],
    user_city: Optional[str],
    user_province: Optional[str],
) -> None:
    """Log how many stories fall in local / province / national / other buckets."""
    uc = _norm(user_city) or None
    up = _norm(user_province) or None
    if not uc and not up:
        print("[location_rank] no user location — ordering by rank_score only")
        return

    counts = {"local": 0, "province": 0, "national": 0, "other": 0}
    for a in sorted_articles:
        b = classify_bucket(a.get("region"), uc, up)
        if b in counts:
            counts[b] += 1

    print(
        "[location_rank] selected_location "
        f"city={uc!r} province={up!r} "
        f"in_feed local={counts['local']} province={counts['province']} "
        f"national={counts['national']} other={counts['other']} total={len(sorted_articles)}"
    )


def log_top_ranked_with_location(
    sorted_articles: List[Dict],
    user_city: Optional[str],
    user_province: Optional[str],
    limit: int = 8,
) -> None:
    """Log top stories with effective rank and boost reason."""
    uc = _norm(user_city) or None
    up = _norm(user_province) or None
    if not sorted_articles:
        return
    if not uc and not up:
        return

    print(f"[location_rank] top {min(limit, len(sorted_articles))} after location ordering:")
    for i, a in enumerate(sorted_articles[:limit], start=1):
        reg = (a.get("region") or "")[:40]
        base = float(a.get("rank_score") or 0.0)
        boost, reason = location_boost_and_reason(a.get("region"), uc, up)
        eff = base + boost
        title = (a.get("title") or "")[:70]
        print(
            f"[location_rank]  #{i} effective={eff:.2f} base_rank={base:.2f} "
            f"boost={boost:.2f} ({reason}) region={reg!r} title={title!r}"
        )
