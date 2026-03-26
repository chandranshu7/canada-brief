"""
Local-mode feed selection: registry-first (see source_registry), optional pattern fallback.

If the registry already has city-tier feeds for the requested city, only those + province +
national are used (no unrelated cities). Unsupported cities map to a nearby metro hub +
province feeds before national-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from services.canada_locations import (
    has_strong_local_coverage,
    location_meta_for_log,
)
from services.metro_fallback import metro_hub_for_city
from services.source_registry import (
    COVERAGE_CITY,
    COVERAGE_NATIONAL,
    COVERAGE_PROVINCE,
    SourceEntry,
    get_local_feed_entries_for_scoped,
    has_city_tier_in_entries,
)


@dataclass(frozen=True)
class LocalFeedSlugs:
    cbc_slug: str
    global_slug: str
    citynews_subdomain: str


@dataclass
class LocalFeedPlan:
    """Result of building the Local-mode ingest list + API metadata."""

    entries: List[SourceEntry]
    metro_hub: Optional[str]
    has_exact_city_registry: bool
    strong_dataset_coverage: bool
    dynamic_city_feeds_injected: bool
    metro_hub_feeds_included: bool
    province_fallback_only: bool
    fallback_type: str  # exact_city | metro_fallback | province_fallback | national_only


# Override slugs when auto-guess is wrong. Keys: normalized city name.
CITY_LOCAL_SLUGS: Dict[str, LocalFeedSlugs] = {
    "ottawa": LocalFeedSlugs("ottawa", "ottawa", "ottawa"),
    "toronto": LocalFeedSlugs("toronto", "toronto", "toronto"),
    "montreal": LocalFeedSlugs("montreal", "montreal", "montreal"),
    "vancouver": LocalFeedSlugs("vancouver", "vancouver", "vancouver"),
    "calgary": LocalFeedSlugs("calgary", "calgary", "calgary"),
    "edmonton": LocalFeedSlugs("edmonton", "edmonton", "edmonton"),
    "winnipeg": LocalFeedSlugs("winnipeg", "winnipeg", "winnipeg"),
    "halifax": LocalFeedSlugs("halifax", "halifax", "halifax"),
    "regina": LocalFeedSlugs("regina", "regina", "regina"),
    "saskatoon": LocalFeedSlugs("saskatoon", "saskatoon", "saskatoon"),
}


def _norm_city_key(city: str) -> str:
    return re.sub(r"[^a-z]+", "", (city or "").strip().lower())


def _slugify_global(city: str) -> str:
    s = (city or "").strip().lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "canada"


def _slugify_cbc(city: str) -> str:
    s = (city or "").strip().lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or "canada"


def _slugify_citynews(city: str) -> str:
    s = (city or "").strip().lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or "city"


def resolve_slugs(city: str) -> LocalFeedSlugs:
    key = _norm_city_key(city)
    if key in CITY_LOCAL_SLUGS:
        return CITY_LOCAL_SLUGS[key]
    return LocalFeedSlugs(
        cbc_slug=_slugify_cbc(city),
        global_slug=_slugify_global(city),
        citynews_subdomain=_slugify_citynews(city),
    )


def _dedupe_entries(entries: List[SourceEntry]) -> List[SourceEntry]:
    seen = set()
    out: List[SourceEntry] = []
    for e in entries:
        u = (e.feed_url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(e)
    return out


def _dynamic_pattern_entries(city: str, province: str) -> List[SourceEntry]:
    """Last-resort feeds when registry has no city-tier rows for this location."""
    c = (city or "").strip()
    p = (province or "").strip()
    slugs = resolve_slugs(c)
    key_base = _norm_city_key(c) or "city"
    return [
        SourceEntry(
            registry_key=f"local_dyn_{key_base}_cbc",
            city=c,
            province=p,
            source_name=f"CBC {c}",
            source_group="CBC",
            feed_url=f"https://www.cbc.ca/webfeed/rss/rss-canada-{slugs.cbc_slug}",
            coverage_level=COVERAGE_CITY,
            priority=5,
            active=True,
            include_in_general=False,
        ),
        SourceEntry(
            registry_key=f"local_dyn_{key_base}_global",
            city=c,
            province=p,
            source_name=f"Global News {c}",
            source_group="Global",
            feed_url=f"https://globalnews.ca/{slugs.global_slug}/feed/",
            coverage_level=COVERAGE_CITY,
            priority=6,
            active=True,
            include_in_general=False,
        ),
        SourceEntry(
            registry_key=f"local_dyn_{key_base}_citynews",
            city=c,
            province=p,
            source_name=f"CityNews {c}",
            source_group="CityNews",
            feed_url=f"https://{slugs.citynews_subdomain}.citynews.ca/feed/",
            coverage_level=COVERAGE_CITY,
            priority=7,
            active=True,
            include_in_general=False,
        ),
    ]


def _metro_rows_present(entries: List[SourceEntry], hub: Optional[str]) -> bool:
    if not hub:
        return False
    hl = hub.strip().lower()
    return any(
        (e.coverage_level or "").lower() in ("city", "civic")
        and (e.city or "").strip().lower() == hl
        for e in entries
    )


def _has_province_rows(entries: List[SourceEntry]) -> bool:
    return any((e.coverage_level or "").lower() == COVERAGE_PROVINCE for e in entries)


def _compute_fallback_type(
    *,
    has_exact_registry: bool,
    dynamic_injected: bool,
    hub: Optional[str],
    metro_included: bool,
    merged: List[SourceEntry],
) -> str:
    if has_exact_registry or dynamic_injected:
        return "exact_city"
    if hub and metro_included:
        return "metro_fallback"
    if _has_province_rows(merged):
        return "province_fallback"
    return "national_only"


def build_local_feed_plan(city: str, province: str) -> LocalFeedPlan:
    """
    Registry-scoped feeds for Local mode: exact city → metro hub (if mapped) → province → national.

    If the registry has city-tier feeds for the user city, use those (no duplicate hub).

    If not, and the dataset marks strong local coverage, inject dynamic city RSS patterns
    plus scoped feeds including optional metro hub.

    Otherwise (unsupported city): include metro hub feeds when mapped, else province + national.
    """
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return LocalFeedPlan(
            entries=[],
            metro_hub=None,
            has_exact_city_registry=False,
            strong_dataset_coverage=False,
            dynamic_city_feeds_injected=False,
            metro_hub_feeds_included=False,
            province_fallback_only=False,
            fallback_type="national_only",
        )

    meta = location_meta_for_log(c, p)
    hub = metro_hub_for_city(c)

    core_no_hub = get_local_feed_entries_for_scoped(c, p, metro_hub=None)
    has_city = has_city_tier_in_entries(core_no_hub, c)
    strong = has_strong_local_coverage(c, p)
    dynamic_injected = False
    province_fb_only = False

    if has_city:
        merged = list(core_no_hub)
        metro_included = False
    elif strong:
        scoped_with_hub = get_local_feed_entries_for_scoped(c, p, metro_hub=hub)
        merged = _dynamic_pattern_entries(c, p) + scoped_with_hub
        dynamic_injected = True
        merged.sort(
            key=lambda e: (
                {"city": 0, "civic": 0, "province": 1, "national": 2}.get(
                    (e.coverage_level or "").lower(), 9
                ),
                e.priority,
                e.registry_key,
            )
        )
        metro_included = _metro_rows_present(merged, hub)
    else:
        merged = list(get_local_feed_entries_for_scoped(c, p, metro_hub=hub))
        province_fb_only = not _metro_rows_present(merged, hub) and not has_city
        metro_included = _metro_rows_present(merged, hub)

    merged = _dedupe_entries(merged)

    fb = _compute_fallback_type(
        has_exact_registry=has_city,
        dynamic_injected=dynamic_injected,
        hub=hub,
        metro_included=metro_included,
        merged=merged,
    )

    print(
        "[local_source] "
        f"location={meta} "
        f"registry_city_tier={has_city} "
        f"strong_dataset_coverage={strong} "
        f"metro_hub={hub!r} "
        f"metro_hub_feeds_included={metro_included} "
        f"dynamic_city_feeds_injected={dynamic_injected} "
        f"province_plus_national_only={province_fb_only} "
        f"fallback_type={fb!r}"
    )

    return LocalFeedPlan(
        entries=merged,
        metro_hub=hub,
        has_exact_city_registry=has_city,
        strong_dataset_coverage=strong,
        dynamic_city_feeds_injected=dynamic_injected,
        metro_hub_feeds_included=metro_included,
        province_fallback_only=province_fb_only,
        fallback_type=fb,
    )


def build_local_feed_entries(city: str, province: str) -> List[SourceEntry]:
    return build_local_feed_plan(city, province).entries


def local_coverage_for_api(city: str, province: str) -> Dict[str, object]:
    """Lightweight metadata for /news JSON (no DB reads)."""
    plan = build_local_feed_plan(city, province)
    return local_coverage_from_plan(plan)


def local_coverage_from_plan(plan: LocalFeedPlan) -> Dict[str, object]:
    """Serialize `LocalFeedPlan` for JSON (no extra registry work)."""
    return {
        "fallback_type": plan.fallback_type,
        "metro_hub": plan.metro_hub,
        "has_exact_city_registry": plan.has_exact_city_registry,
        "strong_dataset_coverage": plan.strong_dataset_coverage,
        "dynamic_city_feeds_injected": plan.dynamic_city_feeds_injected,
        "metro_hub_feeds_included": plan.metro_hub_feeds_included,
        "province_fallback_only": plan.province_fallback_only,
    }


def describe_local_feed_plan(
    city: str, province: str, plan: Optional[LocalFeedPlan] = None
) -> Tuple[List[str], Dict[str, str]]:
    pl = plan or build_local_feed_plan(city, province)
    urls = [e.feed_url for e in pl.entries]
    sl = resolve_slugs(city)
    meta = {
        "cbc_pattern": f"rss-canada-{sl.cbc_slug}",
        "global_pattern": f"/{sl.global_slug}/feed/",
        "citynews_pattern": f"{sl.citynews_subdomain}.citynews.ca/feed/",
        "fallback_type": pl.fallback_type,
        "metro_hub": pl.metro_hub or "",
    }
    return urls, meta
