"""
Daily Brief (V1): top 5 stories from the general feed order, deduped, no AI.

Uses the same rank order as `get_articles_page` (rank_score DESC, id DESC),
stable dedupe (`dedupe_articles_stable`), then a brief-specific sort that prefers
same-day (UTC) stories when scores are close. Same display-summary rules as `/news`.

Cache: short TTL + invalidation when `news.id` grows so the brief tracks ingest and
does not stay frozen for a whole UTC day.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Tuple

from database import get_articles_page, get_news_max_id
from services.deterministic_summary import clamp_summary_display
from services.feed_dedupe import dedupe_articles_stable
from services.ranking import _parse_published_for_rank, _utc_naive
from services.summarize import display_summary_for_response

FETCH_WINDOW = 80
TOP_N = 5
GENERATION_SOURCE = "general_news_ranked_deduped_v2"

# Refresh at most this often unless max(id) changes (new ingest).
_CACHE_TTL_SEC = float(os.environ.get("DAILY_BRIEF_CACHE_TTL_SEC", "120"))

_cache_payload: Optional[Dict[str, Any]] = None
_cache_generated_at_monotonic: float = 0.0
_cached_max_news_id: int = -1

_BRIEF_PLACEHOLDER_IMAGE_URLS = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=60",
)


def _placeholder_image_for_row(row: Dict[str, Any]) -> str:
    title = (row.get("title") or "").lower()
    link = (row.get("link") or "").lower()
    src = (row.get("source") or "").lower()
    digest = hashlib.md5(f"{title}|{link}|{src}".encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(_BRIEF_PLACEHOLDER_IMAGE_URLS)
    return _BRIEF_PLACEHOLDER_IMAGE_URLS[idx]


def _dedupe_story_images(stories: List[Dict[str, Any]]) -> None:
    seen: set[str] = set()
    replaced = 0

    def _image_key(url: str) -> str:
        raw = (url or "").strip().lower()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
            host = (p.netloc or "").lower()
            path = (p.path or "").lower().rstrip("/")
            if host and path:
                return f"{host}{path}"
        except Exception:
            pass
        return raw

    for s in stories:
        raw = (s.get("image_url") or "").strip()
        if not raw:
            s["image_url"] = _placeholder_image_for_row(s)
            replaced += 1
            continue
        key = _image_key(raw)
        if key in seen:
            s["image_url"] = _placeholder_image_for_row(s)
            replaced += 1
            continue
        seen.add(key)
    if replaced > 0:
        print(f"[daily_brief] image_dedupe replaced={replaced}")


def _brief_summary_for_row(row: Dict[str, Any]) -> str:
    ex = (row.get("rss_excerpt") or "").strip() or None
    st = (row.get("summary_status") or "pending").strip().lower()
    text, _src = display_summary_for_response(
        title=row.get("title") or "",
        summary=row.get("summary"),
        rss_excerpt=ex,
        summary_status=st,
    )
    return clamp_summary_display(text or "")


def _category_label(row: Dict[str, Any]) -> str:
    topic = (row.get("topic_category") or "").strip()
    if topic:
        return topic
    return (row.get("category") or "").strip()


def _estimate_read_seconds(summaries: List[str]) -> Tuple[int, str]:
    words = sum(len((s or "").split()) for s in summaries)
    # ~200 words per minute
    sec = max(20, min(180, int(round(words / 200.0 * 60))))
    if sec < 60:
        label = f"~{sec} sec"
    else:
        m = max(1, int(round(sec / 60.0)))
        label = f"~{m} min"
    return sec, label


def _today_utc_date():
    return datetime.now(timezone.utc).date()


def _brief_selection_score(row: Dict[str, Any]) -> float:
    """
    Prefer higher rank_score; add a modest boost for stories published today (UTC)
    so the brief favors fresher same-day items when the feed has newer coverage.
    """
    rs = float(row.get("rank_score") or 0.0)
    bonus = 0.0
    dt = _parse_published_for_rank(row.get("published"))
    if dt is not None:
        try:
            d = _utc_naive(dt).date()
            if d == _today_utc_date():
                bonus = 14.0
        except Exception:
            pass
    return rs + bonus


def _sort_brief_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable editorial order: selection score desc, then id desc."""
    out = list(rows)
    out.sort(
        key=lambda r: (_brief_selection_score(r), r.get("id") or 0),
        reverse=True,
    )
    return out


def _max_last_updated_iso(stories: List[Dict[str, Any]]) -> Optional[str]:
    best: Optional[str] = None
    for s in stories:
        lu = (s.get("last_updated_at") or "").strip()
        if not lu:
            continue
        if best is None or lu > best:
            best = lu
    return best


def _build_daily_brief_payload_uncached() -> Dict[str, Any]:
    brief_date = datetime.now(timezone.utc).date().isoformat()
    brief_generated_at = datetime.now(timezone.utc).isoformat()
    max_id = get_news_max_id()

    rows = get_articles_page(0, FETCH_WINDOW)
    deduped, removed_n, dup_keys = dedupe_articles_stable(rows)
    ranked = _sort_brief_candidates(deduped)
    selected = ranked[:TOP_N]
    ids = [r.get("id") for r in selected]

    stories: List[Dict[str, Any]] = []
    summaries_for_time: List[str] = []

    for row in selected:
        row = dict(row)
        summary = _brief_summary_for_row(row)
        summaries_for_time.append(summary)
        stories.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "summary": summary,
                "source": row.get("source") or "",
                "published": row.get("published"),
                "category": _category_label(row),
                "region": row.get("region"),
                "image_url": row.get("image_url"),
                "link": row.get("link") or "",
            }
        )

    _dedupe_story_images(stories)

    sec, label = _estimate_read_seconds(summaries_for_time)
    source_ts = _max_last_updated_iso(selected)

    payload: Dict[str, Any] = {
        "brief_date": brief_date,
        "brief_generated_at": brief_generated_at,
        "brief_source_timestamp": source_ts,
        "brief_max_news_id": max_id,
        "estimated_read_time_seconds": sec,
        "estimated_read_time_label": label,
        "generation_source": GENERATION_SOURCE,
        "stories": stories,
    }

    print(
        f"[daily_brief] brief_date={brief_date} brief_generated_at={brief_generated_at} "
        f"brief_source_timestamp={source_ts!r} brief_max_news_id={max_id} "
        f"source={GENERATION_SOURCE} generation=build selected_ids={ids} "
        f"fetch_window={FETCH_WINDOW} dedupe_removed={removed_n} "
        f"cache_ttl_sec={_CACHE_TTL_SEC}"
    )
    if removed_n and dup_keys:
        print(f"[daily_brief] dedupe_sample_keys={dup_keys[:8]!r}")

    return payload


def _cache_stale() -> bool:
    global _cache_payload, _cache_generated_at_monotonic, _cached_max_news_id
    if _cache_payload is None:
        return True
    now = time.monotonic()
    if now - _cache_generated_at_monotonic > _CACHE_TTL_SEC:
        return True
    try:
        current_max = get_news_max_id()
    except Exception:
        return True
    if current_max != _cached_max_news_id:
        return True
    return False


def get_daily_brief_payload() -> Dict[str, Any]:
    """
    Cached snapshot with TTL + max(id) invalidation: top 5 general ranked stories
    after stable dedupe and brief re-ranking.
    """
    global _cache_payload, _cache_generated_at_monotonic, _cached_max_news_id

    if not _cache_stale():
        ids = [s.get("id") for s in _cache_payload.get("stories", [])]
        print(
            f"[daily_brief] generation=cached selected_ids={ids} "
            f"brief_generated_at={_cache_payload.get('brief_generated_at')!r} "
            f"cached_max_news_id={_cached_max_news_id}"
        )
        return _cache_payload

    _cache_payload = _build_daily_brief_payload_uncached()
    _cache_generated_at_monotonic = time.monotonic()
    _cached_max_news_id = int(_cache_payload.get("brief_max_news_id") or -1)
    return _cache_payload
