"""
Central Canadian news source registry.

Each SourceEntry is one RSS line. Add cities by extending METRO_SLUGS / province rows /
national rows — avoid scattering URLs across fetch_news or local_source_config.

General mode: entries with include_in_general=True (national + major regional anchors).
Local mode: entries scoped to the user city + province + national (never other cities).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# Valid coverage_level values stored on articles and used for tier logic.
COVERAGE_CITY = "city"
COVERAGE_PROVINCE = "province"
COVERAGE_NATIONAL = "national"
COVERAGE_CIVIC = "civic"


@dataclass(frozen=True)
class SourceEntry:
    """One RSS source row."""

    registry_key: str
    city: Optional[str]
    province: str
    source_name: str
    source_group: str
    feed_url: str
    coverage_level: str  # city | province | national | civic
    priority: int
    active: bool = True
    # When True, this feed is part of the General-mode ingest pool (national + major regional).
    include_in_general: bool = False


def _coverage_sort_key(level: str) -> int:
    lv = (level or "").strip().lower()
    if lv in (COVERAGE_CITY, COVERAGE_CIVIC):
        return 0
    if lv == COVERAGE_PROVINCE:
        return 1
    if lv == COVERAGE_NATIONAL:
        return 2
    return 9


def _dedupe_by_url(entries: Sequence[SourceEntry]) -> List[SourceEntry]:
    seen = set()
    out: List[SourceEntry] = []
    for e in entries:
        u = (e.feed_url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(e)
    return out


def _S(
    key: str,
    city: Optional[str],
    province: str,
    name: str,
    group: str,
    url: str,
    level: str,
    priority: int,
    *,
    active: bool = True,
    include_in_general: bool = False,
) -> SourceEntry:
    return SourceEntry(
        registry_key=key,
        city=city,
        province=province,
        source_name=name,
        source_group=group,
        feed_url=url,
        coverage_level=level,
        priority=priority,
        active=active,
        include_in_general=include_in_general,
    )


# (display city, province, global/cbc/citynews URL slug segment)
_METRO_SLUGS: Tuple[Tuple[str, str, str], ...] = (
    ("Ottawa", "Ontario", "ottawa"),
    ("Toronto", "Ontario", "toronto"),
    ("Montreal", "Quebec", "montreal"),
    ("Vancouver", "British Columbia", "vancouver"),
    ("Calgary", "Alberta", "calgary"),
    ("Edmonton", "Alberta", "edmonton"),
    ("Winnipeg", "Manitoba", "winnipeg"),
    ("Halifax", "Nova Scotia", "halifax"),
    ("Regina", "Saskatchewan", "regina"),
    ("Saskatoon", "Saskatchewan", "saskatoon"),
)


def _metro_city_entries() -> List[SourceEntry]:
    """CBC + Global + CityNews anchors per metro (Local + tagging); not in General pool."""
    rows: List[SourceEntry] = []
    for city, prov, slug in _METRO_SLUGS:
        cbc_active = slug != "ottawa"  # Ottawa CBC URL often flaky; Global remains primary.
        rows.append(
            _S(
                f"{slug}_global_city",
                city,
                prov,
                f"Global News {city}",
                "Global",
                f"https://globalnews.ca/{slug}/feed/",
                COVERAGE_CITY,
                10,
                include_in_general=False,
            )
        )
        rows.append(
            _S(
                f"{slug}_cbc_city",
                city,
                prov,
                f"CBC {city}",
                "CBC",
                f"https://www.cbc.ca/webfeed/rss/rss-canada-{slug}",
                COVERAGE_CITY,
                11,
                active=cbc_active,
                include_in_general=False,
            )
        )
        rows.append(
            _S(
                f"{slug}_citynews_city",
                city,
                prov,
                f"CityNews {city}",
                "CityNews",
                f"https://{slug}.citynews.ca/feed/",
                COVERAGE_CITY,
                12,
                include_in_general=False,
            )
        )
    return rows


def _province_regional_entries() -> List[SourceEntry]:
    """Major provincial/regional CBC anchors (General + Local province tier)."""
    return [
        _S(
            "bc_cbc_province",
            None,
            "British Columbia",
            "CBC British Columbia",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-britishcolumbia",
            COVERAGE_PROVINCE,
            20,
            include_in_general=True,
        ),
        _S(
            "ab_cbc_province",
            None,
            "Alberta",
            "CBC Alberta",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-alberta",
            COVERAGE_PROVINCE,
            21,
            include_in_general=True,
        ),
        _S(
            "sk_cbc_province",
            None,
            "Saskatchewan",
            "CBC Saskatchewan",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-saskatchewan",
            COVERAGE_PROVINCE,
            21,
            include_in_general=True,
        ),
        _S(
            "mb_cbc_province",
            None,
            "Manitoba",
            "CBC Manitoba",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-manitoba",
            COVERAGE_PROVINCE,
            20,
            include_in_general=True,
        ),
        _S(
            "on_cbc_province",
            None,
            "Ontario",
            "CBC Ontario",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-ontario",
            COVERAGE_PROVINCE,
            22,
            active=True,
            include_in_general=True,
        ),
        _S(
            "on_global_province",
            None,
            "Ontario",
            "Global News Ontario",
            "Global",
            "https://globalnews.ca/ontario/feed/",
            COVERAGE_PROVINCE,
            23,
            include_in_general=True,
        ),
        _S(
            "qc_cbc_province",
            None,
            "Quebec",
            "CBC Quebec",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-quebec",
            COVERAGE_PROVINCE,
            22,
            active=True,
            include_in_general=True,
        ),
        _S(
            "ns_cbc_province",
            None,
            "Nova Scotia",
            "CBC Nova Scotia",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-canada-novascotia",
            COVERAGE_PROVINCE,
            25,
            include_in_general=True,
        ),
    ]


def _national_entries() -> List[SourceEntry]:
    return [
        _S(
            "national_global_top",
            None,
            "",
            "Global News - Top Stories",
            "Global",
            "https://globalnews.ca/feed/",
            COVERAGE_NATIONAL,
            100,
            include_in_general=True,
        ),
        _S(
            "national_global_canada",
            None,
            "",
            "Global News - Canada",
            "Global",
            "https://globalnews.ca/canada/feed/",
            COVERAGE_NATIONAL,
            101,
            include_in_general=True,
        ),
        _S(
            "national_global_politics",
            None,
            "",
            "Global News - Politics",
            "Global",
            "https://globalnews.ca/politics/feed/",
            COVERAGE_NATIONAL,
            102,
            include_in_general=True,
        ),
        _S(
            "national_cbc_top",
            None,
            "",
            "CBC News",
            "CBC",
            "https://www.cbc.ca/webfeed/rss/rss-topstories",
            COVERAGE_NATIONAL,
            110,
            include_in_general=True,
        ),
        # Google News RSS (Canada) — fast, broad; merged into General pool with CBC/Global.
        _S(
            "gnews_canada_general",
            None,
            "",
            "Google News — Canada",
            "Google News",
            "https://news.google.com/rss/search?q=Canada&hl=en-CA&gl=CA&ceid=CA:en",
            COVERAGE_NATIONAL,
            95,
            include_in_general=True,
        ),
        _S(
            "gnews_canada_ai",
            None,
            "",
            "Google News — Canada AI",
            "Google News",
            "https://news.google.com/rss/search?q=Canada+AI&hl=en-CA&gl=CA&ceid=CA:en",
            COVERAGE_NATIONAL,
            96,
            include_in_general=True,
        ),
        _S(
            "gnews_canada_immigration",
            None,
            "",
            "Google News — Canada immigration",
            "Google News",
            "https://news.google.com/rss/search?q=Canada+immigration&hl=en-CA&gl=CA&ceid=CA:en",
            COVERAGE_NATIONAL,
            97,
            include_in_general=True,
        ),
        _S(
            "gnews_canada_housing",
            None,
            "",
            "Google News — Canada housing",
            "Google News",
            "https://news.google.com/rss/search?q=Canada+housing&hl=en-CA&gl=CA&ceid=CA:en",
            COVERAGE_NATIONAL,
            98,
            include_in_general=True,
        ),
        _S(
            "gnews_canada_jobs",
            None,
            "",
            "Google News — Canada jobs",
            "Google News",
            "https://news.google.com/rss/search?q=Canada+jobs&hl=en-CA&gl=CA&ceid=CA:en",
            COVERAGE_NATIONAL,
            99,
            include_in_general=True,
        ),
    ]


def _build_canada_source_entries() -> Tuple[SourceEntry, ...]:
    parts: List[SourceEntry] = []
    parts.extend(_metro_city_entries())
    parts.extend(_province_regional_entries())
    parts.extend(_national_entries())
    return tuple(parts)


CANADA_SOURCE_ENTRIES: Tuple[SourceEntry, ...] = _build_canada_source_entries()


def all_entries() -> Tuple[SourceEntry, ...]:
    return CANADA_SOURCE_ENTRIES


def active_entries() -> List[SourceEntry]:
    return [e for e in CANADA_SOURCE_ENTRIES if e.active]


def registry_stats() -> Dict[str, int]:
    """Counts for startup / ingest logs."""
    total = len(CANADA_SOURCE_ENTRIES)
    act = len(active_entries())
    gen = len([e for e in active_entries() if e.include_in_general])
    return {
        "entries_defined": total,
        "entries_active": act,
        "entries_active_general_pool": gen,
    }


def get_general_feed_entries_for_ingest() -> List[SourceEntry]:
    """
    General-mode ingest: national + major regional (include_in_general=True).
    City-only metro feeds stay out of the General pool to avoid duplicating every local RSS.
    """
    pool = [e for e in active_entries() if e.include_in_general]
    pool.sort(key=lambda e: (e.priority, e.registry_key))
    return _dedupe_by_url(pool)


def get_feed_entries_for_ingest() -> List[SourceEntry]:
    """Backward-compatible alias."""
    return get_general_feed_entries_for_ingest()


def _local_scope_sort_key(
    e: SourceEntry, user_city_lc: str, metro_hub_lc: str
) -> Tuple[int, int, str]:
    """Order: user city → metro hub city → province → national."""
    cl = (e.coverage_level or "").strip().lower()
    ec = (e.city or "").strip().lower()
    if cl in (COVERAGE_CITY, COVERAGE_CIVIC):
        if ec == user_city_lc:
            return (0, e.priority, e.registry_key)
        if metro_hub_lc and ec == metro_hub_lc:
            return (1, e.priority, e.registry_key)
        return (9, e.priority, e.registry_key)
    if cl == COVERAGE_PROVINCE:
        return (2, e.priority, e.registry_key)
    if cl == COVERAGE_NATIONAL:
        return (3, e.priority, e.registry_key)
    return (9, e.priority, e.registry_key)


def get_local_feed_entries_for_scoped(
    city: str, province: str, metro_hub: Optional[str] = None
) -> List[SourceEntry]:
    """
    Local-mode feeds for one (city, province): matching city/civic rows, optional metro
    hub city rows (same province), province rows, and national rows — never unrelated cities.
    """
    c = (city or "").strip().lower()
    p = (province or "").strip().lower()
    if not c or not p:
        return []

    hub = (metro_hub or "").strip().lower()
    if hub == c:
        hub = ""

    selected: List[SourceEntry] = []
    for e in active_entries():
        cl = (e.coverage_level or "").strip().lower()
        if cl in (COVERAGE_CITY, COVERAGE_CIVIC):
            ec = (e.city or "").strip().lower()
            if ec == c:
                selected.append(e)
            elif hub and ec == hub:
                selected.append(e)
        elif cl == COVERAGE_PROVINCE:
            ep = (e.province or "").strip().lower()
            if ep == p:
                selected.append(e)
        elif cl == COVERAGE_NATIONAL:
            selected.append(e)

    selected.sort(key=lambda e: _local_scope_sort_key(e, c, hub))
    return _dedupe_by_url(selected)


def has_city_tier_in_entries(entries: Sequence[SourceEntry], city: str) -> bool:
    """True if list already has a city/civic feed for this city (skip dynamic duplicate)."""
    cc = (city or "").strip().lower()
    if not cc:
        return False
    for e in entries:
        cl = (e.coverage_level or "").strip().lower()
        if cl not in (COVERAGE_CITY, COVERAGE_CIVIC):
            continue
        if (e.city or "").strip().lower() == cc:
            return True
    return False


def entry_by_registry_key(key: str) -> Optional[SourceEntry]:
    for e in CANADA_SOURCE_ENTRIES:
        if e.registry_key == key:
            return e
    return None


def source_display_names_for_city(city: str) -> Tuple[str, ...]:
    c = (city or "").strip()
    if not c:
        return ()
    names = sorted(
        {
            e.source_name
            for e in active_entries()
            if e.coverage_level in (COVERAGE_CITY, COVERAGE_CIVIC)
            and e.city
            and e.city.strip().lower() == c.lower()
        }
    )
    return tuple(names)


def sources_for_local_fallback(
    city: str, province: str, metro_hub: Optional[str] = None
) -> Dict[str, List[str]]:
    c = (city or "").strip()
    p = (province or "").strip()
    mh = (metro_hub or "").strip()
    scoped = get_local_feed_entries_for_scoped(c, p, metro_hub=mh or None)
    user_lc = c.lower()
    hub_lc = mh.lower() if mh else ""
    city_keys = [
        e.registry_key
        for e in scoped
        if e.coverage_level in (COVERAGE_CITY, COVERAGE_CIVIC)
        and (e.city or "").strip().lower() == user_lc
    ]
    metro_keys = [
        e.registry_key
        for e in scoped
        if e.coverage_level in (COVERAGE_CITY, COVERAGE_CIVIC)
        and hub_lc
        and (e.city or "").strip().lower() == hub_lc
    ]
    prov_keys = [
        e.registry_key for e in scoped if e.coverage_level == COVERAGE_PROVINCE
    ]
    national_keys = [
        e.registry_key for e in scoped if e.coverage_level == COVERAGE_NATIONAL
    ]
    return {
        "city": city_keys,
        "metro": metro_keys,
        "province": prov_keys,
        "national": national_keys,
    }
