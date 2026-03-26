"""
local_feed.py — Local mode: world filter, strict location tiers, regional source boosts.

Tier order (primary sort key; never outranked by rank_score alone):
  0 = user's selected city only
  1 = metro hub (nearby supported hub, e.g. Toronto for Brampton)
  2 = user's province (provincial / province-wide region)
  3 = true Canada-wide (national feed + region Canada / non-geographic)
  4 = unrelated — dropped (other provinces, other cities, geo-tagged national rows)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from services.local_source_config import LocalFeedPlan, build_local_feed_plan
from services.location_ranking import (
    CITY_TO_PROVINCE,
    PROVINCE_NAMES,
    article_province_for_region,
    location_boost_and_reason,
)
from services.source_registry import source_display_names_for_city, sources_for_local_fallback

# Curated regional source hints (substring match on `source`). Extend per city over time.
CITY_SOURCE_NEEDLES: Dict[str, Tuple[str, ...]] = {
    "Ottawa": (
        "Ottawa",
        "CBC Ottawa",
        "Global News Ottawa",
        "CTV News Ottawa",
    ),
    "Toronto": (
        "Toronto",
        "CBC Toronto",
        "Global News Toronto",
        "CTV News Toronto",
    ),
    "Montreal": (
        "Montreal",
        "Montréal",
        "CBC Montreal",
        "CBC Montréal",
        "Global News Montreal",
        "Radio-Canada",
        "ICI",
        "Québec",
        "Quebec",
    ),
    "Vancouver": (
        "Vancouver",
        "CBC Vancouver",
        "Global News BC",
        "British Columbia",
    ),
    "Calgary": ("Calgary", "CBC Calgary", "Global News Calgary", "Calgary Herald"),
    "Edmonton": ("Edmonton", "CBC Edmonton", "Global News Edmonton"),
    "Winnipeg": ("Winnipeg", "CBC Manitoba", "Global News Winnipeg"),
    "Halifax": ("Halifax", "Nova Scotia", "CBC Nova Scotia", "Global News Atlantic"),
    "Regina": ("Regina", "Saskatchewan", "CBC Saskatchewan", "Global News Regina"),
    "Saskatoon": ("Saskatoon", "Saskatchewan", "CBC Saskatchewan", "Global News Saskatoon"),
}

_LOCAL_SOURCE_BOOST = 38.0


def curated_needles_for_city(city: str) -> Tuple[str, ...]:
    reg = source_display_names_for_city(city)
    if reg:
        return reg
    return CITY_SOURCE_NEEDLES.get(city.strip(), ())


def local_source_boost(
    source: Optional[str],
    city: str,
    article: Optional[Dict] = None,
    *,
    metro_hub: Optional[str] = None,
) -> float:
    if article:
        cc = (article.get("coverage_city") or "").strip()
        uc = (city or "").strip()
        if uc and cc and cc.lower() == uc.lower():
            return _LOCAL_SOURCE_BOOST
        mh = (metro_hub or "").strip()
        if mh:
            if cc and cc.lower() == mh.lower():
                return _LOCAL_SOURCE_BOOST
            r = (article.get("region") or "").strip()
            if r and r.lower() == mh.lower():
                return _LOCAL_SOURCE_BOOST
            needles = curated_needles_for_city(mh)
            s = (source or "").lower()
            for n in needles:
                if n.lower() in s:
                    return _LOCAL_SOURCE_BOOST
    needles = curated_needles_for_city(city)
    if not needles:
        return 0.0
    s = (source or "").lower()
    for n in needles:
        if n.lower() in s:
            return _LOCAL_SOURCE_BOOST
    return 0.0


def exclude_in_local_feed(article: Dict) -> bool:
    reg = (article.get("region") or "").strip()
    if reg == "World":
        return True
    cat = (article.get("category") or "").strip().lower()
    if cat == "world":
        return True
    return False


def effective_local_score(
    article: Dict,
    city: str,
    province: str,
    metro_hub: Optional[str] = None,
) -> float:
    base = float(article.get("rank_score") or 0.0)
    lb, _ = location_boost_and_reason(article.get("region"), city, province)
    sb = local_source_boost(
        article.get("source"), city, article, metro_hub=metro_hub
    )
    return base + lb + sb


def classify_local_tier_for_article(
    article: Dict,
    user_city: str,
    user_province: str,
    metro_hub: Optional[str] = None,
) -> int:
    """
    Strict local tiers for the selected (city, province, metro_hub):

    0 = user's city only (region label or registry city match).
    1 = metro hub (nearby supported hub city / its local feeds).
    2 = user's province (province-wide / provincial feeds).
    3 = true Canada-wide (national pool + region Canada / non-geographic).
    4 = unrelated — dropped.

    National RSS rows that infer_region() tagged as a city/province stay dropped unless
    they match the metro hub path.
    """
    uc = (user_city or "").strip()
    up = (user_province or "").strip()
    mh = (metro_hub or "").strip()
    ucl = uc.lower() if uc else ""
    mhl = mh.lower() if mh else ""

    cl = (article.get("coverage_level") or "").strip().lower()
    cc = (article.get("coverage_city") or "").strip()
    cp = (article.get("coverage_province") or "").strip()
    ccl = cc.lower() if cc else ""

    r = (article.get("region") or "").strip()
    r_low = r.lower()

    # Wrong province (region is another province name)
    if r and r in PROVINCE_NAMES and up and r_low != up.lower():
        return 4

    ap0 = article_province_for_region(r)
    if ap0 and up and ap0.lower() != up.lower():
        return 4

    # Another Canadian city — allow only if it is the mapped metro hub
    if r and r in CITY_TO_PROVINCE and uc and r_low != ucl:
        if not (mhl and r_low == mhl):
            return 4

    # Tier 0: exact home city
    if uc and r and r_low == ucl:
        return 0
    if cl in ("city", "civic") and cc and uc and ccl == ucl:
        return 0

    # Registry city row for a different city — metro hub or unrelated
    if cl in ("city", "civic") and cc and uc and ccl != ucl:
        if mhl and ccl == mhl:
            return 1
        return 4

    # Tier 1: metro hub (region or coverage_city)
    if mhl:
        if r and r_low == mhl:
            return 1
        if cl in ("city", "civic") and cc and ccl == mhl:
            return 1

    # Tier 3: national pool (before province so cl=national wins)
    if cl == "national":
        if r_low == "canada" or r == "" or r == "Other":
            return 3
        if r in CITY_TO_PROVINCE or r in PROVINCE_NAMES:
            return 4
        return 3

    # Tier 2: province scope
    if cl == "province" and cp and up and cp.lower() == up.lower():
        return 2

    if up and r and r_low == up.lower():
        return 2

    return classify_local_tier(r, uc, up, metro_hub)


def classify_local_tier(
    region: Optional[str],
    user_city: str,
    user_province: str,
    metro_hub: Optional[str] = None,
) -> int:
    """
    0 = exact city, 1 = metro hub, 2 = province, 3 = Canada national, 4 = unrelated.
    """
    uc = (user_city or "").strip()
    up = (user_province or "").strip()
    mh = (metro_hub or "").strip()
    mhl = mh.lower() if mh else ""
    r = (region or "").strip()
    if not r:
        return 4
    r_low = r.lower()
    ucl = uc.lower() if uc else ""
    if uc and r_low == ucl:
        return 0
    if mhl and r_low == mhl:
        return 1
    if up and r_low == up.lower():
        return 2
    ap = article_province_for_region(r)
    if up and ap and ap.lower() == up.lower():
        return 2
    if r == "Canada":
        return 3
    return 4


def _tier_sort_key(
    a: Dict,
    city: str,
    province: str,
    metro_hub: Optional[str],
) -> Tuple[int, float, int]:
    t = classify_local_tier_for_article(a, city, province, metro_hub)
    eff = effective_local_score(a, city, province, metro_hub)
    aid = int(a.get("id") or 0)
    return (t, -eff, -aid)


def sort_articles_local_mode(
    articles: List[Dict],
    city: str,
    province: str,
    plan: Optional[LocalFeedPlan] = None,
) -> List[Dict]:
    """
    Tier-first sort, then score within tier.

    Keeps tiers 0–3 (city / metro / province / national); drops tier 4 and world.
    """
    c = (city or "").strip()
    p = (province or "").strip()
    plan = plan or build_local_feed_plan(c, p)
    mh = plan.metro_hub

    before = len(articles)
    filtered = [a for a in articles if not exclude_in_local_feed(a)]
    dropped_world = before - len(filtered)

    ranked = sorted(filtered, key=lambda a: _tier_sort_key(a, c, p, mh))

    kept = [a for a in ranked if classify_local_tier_for_article(a, c, p, mh) <= 3]
    dropped_unrelated = [a for a in ranked if classify_local_tier_for_article(a, c, p, mh) == 4]

    final = kept
    suppressed_unrelated = len(dropped_unrelated)

    log_local_feed_pipeline(
        final,
        kept,
        dropped_unrelated,
        c,
        p,
        plan=plan,
        dropped_world=dropped_world,
        input_count=before,
    )
    return final


def log_local_pagination_debug(
    sorted_full: List[Dict],
    page: int,
    offset: int,
    page_size: int,
    page_rows: List[Dict],
    city: str,
    province: str,
) -> None:
    """
    Once per /news response: full ranked id order, expected slice vs returned rows.
    Detects duplicate ids in the ranked list or injected/mismatched page rows.
    """
    ranked_ids = [a.get("id") for a in sorted_full]
    u = len(set(ranked_ids))
    if len(ranked_ids) != u:
        print(
            f"[local_feed] WARN duplicate ids in ranked local list "
            f"total={len(ranked_ids)} unique={u} ids={ranked_ids}"
        )
    print(
        "[local_feed] ranked_ids_before_pagination "
        f"city={city!r} province={province!r} count={len(ranked_ids)} ids={ranked_ids}"
    )
    expected = ranked_ids[offset : offset + page_size]
    actual = [r.get("id") for r in page_rows]
    print(
        "[local_feed] paginated_ids_this_page "
        f"page={page} offset={offset} page_size={page_size} ids={actual}"
    )
    if expected != actual:
        print(
            "[local_feed] WARN paginated slice mismatch "
            f"expected_ids={expected} actual_ids={actual}"
        )
    if len(actual) != len(set(actual)):
        print(f"[local_feed] WARN duplicate ids in page_rows ids={actual}")


def log_curated_sources(city: str) -> None:
    needles = curated_needles_for_city(city)
    print(
        f"[local_feed] curated_source_needles city={city!r} "
        f"needles={list(needles)}"
    )


def log_local_feed_pipeline(
    final: List[Dict],
    _kept_all: List[Dict],
    dropped_tier4: List[Dict],
    city: str,
    province: str,
    *,
    plan: LocalFeedPlan,
    dropped_world: int = 0,
    input_count: int = 0,
) -> None:
    """Counts by tier; suppression; top stories with tier + score."""
    c = city
    p = province
    mh = plan.metro_hub

    def _t(a: Dict) -> int:
        return classify_local_tier_for_article(a, c, p, mh)

    n_city = sum(1 for a in final if _t(a) == 0)
    n_metro = sum(1 for a in final if _t(a) == 1)
    n_prov = sum(1 for a in final if _t(a) == 2)
    n_nat = sum(1 for a in final if _t(a) == 3)

    reg = sources_for_local_fallback(c, p, metro_hub=mh)
    print(
        "[local_feed] locality_pipeline "
        f"selected_city={c!r} selected_province={p!r} "
        f"supported_city_registry={plan.has_exact_city_registry} "
        f"metro_hub={plan.metro_hub!r} "
        f"metro_fallback_used={plan.metro_hub_feeds_included} "
        f"province_fallback_plan={plan.fallback_type!r} "
        f"input_rows={input_count} filtered_out_world={dropped_world} "
        f"filtered_out_unrelated_tier4={len(dropped_tier4)} "
        f"in_feed city_tier_stories={n_city} metro_tier_stories={n_metro} "
        f"province_tier_stories={n_prov} canada_tier_stories={n_nat} "
        f"total_in_feed_after_strict_filter={len(final)}"
    )
    print(
        "[local_feed] tier_counts "
        f"city={n_city} metro={n_metro} province={n_prov} national={n_nat} "
        f"rejected_unrelated={len(dropped_tier4)}"
    )
    print(
        "[local_feed] final_tier_counts "
        f"exact_city={n_city} metro_fallback={n_metro} province={n_prov} national={n_nat}"
    )
    print(
        "[local_feed] fallback_registry_keys "
        f"city_sources={reg['city']} "
        f"metro_sources={reg['metro']} "
        f"province_sources={reg['province']} "
        f"national_sources={reg['national']}"
    )

    def _keys_in_tier(rows: List[Dict], tier: int) -> List[str]:
        out = sorted(
            {
                (a.get("feed_registry_key") or "").strip()
                for a in rows
                if _t(a) == tier and (a.get("feed_registry_key") or "").strip()
            }
        )
        return out

    print(
        "[local_feed] registry_keys_present_in_sorted_feed "
        f"tier0_city={_keys_in_tier(final, 0)} "
        f"tier1_metro={_keys_in_tier(final, 1)} "
        f"tier2_province={_keys_in_tier(final, 2)} "
        f"tier3_national={_keys_in_tier(final, 3)}"
    )

    print(
        "[local_feed] top_ranked (0=city 1=metro 2=province 3=national 4=drop):"
    )
    needles = curated_needles_for_city(c)
    for i, a in enumerate(final[:10], start=1):
        reg = (a.get("region") or "")[:36]
        tier = _t(a)
        eff = effective_local_score(a, c, p, mh)
        src = (a.get("source") or "")[:48]
        src_hit = needles and any(n.lower() in src.lower() for n in needles)
        title = (a.get("title") or "")[:64]
        frk = (a.get("feed_registry_key") or "")[:40]
        print(
            f"[local_feed]  #{i} tier={tier} effective={eff:.2f} "
            f"source_match={src_hit} registry_key={frk!r} region={reg!r} "
            f"source={src!r} title={title!r}"
        )


def log_local_feed_summary(
    sorted_articles: List[Dict],
    city: str,
    province: str,
) -> None:
    """Legacy hook — detailed logging is in log_local_feed_pipeline."""
    c = (city or "").strip()
    p = (province or "").strip()
    needles = curated_needles_for_city(c)
    source_hits = sum(
        1
        for a in sorted_articles
        if needles
        and any(n.lower() in (a.get("source") or "").lower() for n in needles)
    )
    print(
        f"[local_feed] summary city={c!r} province={p!r} "
        f"total={len(sorted_articles)} curated_source_rows={source_hits}"
    )
