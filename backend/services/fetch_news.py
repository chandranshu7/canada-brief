"""
services/fetch_news.py

Fetches articles from Canadian RSS feeds using requests + feedparser and
returns ready-to-save article dicts, including a fast local summary.
"""

import asyncio
import hashlib
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup

from services.local_source_config import build_local_feed_plan, describe_local_feed_plan
from services.source_registry import (
    SourceEntry,
    get_general_feed_entries_for_ingest,
    registry_stats,
)
from services.topic_classification import assign_topic_category

# Feed RSS fetch: keep tight so one slow host does not block the whole refresh.
REQUEST_TIMEOUT = 5
# asyncio.wait_for wraps each feed fetch (HTTP + parse); slightly above REQUEST_TIMEOUT.
FEED_FETCH_ASYNC_TIMEOUT_SEC = float(REQUEST_TIMEOUT) + 4.0

# Article page fetch (og:image only): separate, slightly shorter timeout.
IMAGE_PAGE_TIMEOUT = 4

# Keep refresh/cold-start latency bounded by limiting synchronous image scraping.
MAX_SYNC_IMAGE_ENRICH_PER_INGEST = int(
    os.environ.get("MAX_SYNC_IMAGE_ENRICH_PER_INGEST", "15")
)

# After dedupe + sort, cap how many stories we ingest (cluster + store). No bulk AI here.
MAX_INGEST_ARTICLES = 150

# Legacy cap removed: all stories run the image pipeline; repeated URLs use _PAGE_IMAGE_CACHE.

# Browser-like headers reduce 403/blocked responses from some CDNs and news sites.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
}

# Article HTML fetch (og:image + body <img>).
HTML_PAGE_HEADERS = {
    **HTTP_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# When no image is found anywhere else, every story still gets a valid URL.
GLOBAL_FALLBACK_IMAGE_URL = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    "?auto=format&fit=crop&w=1200&q=60"
)

# In-process cache: normalized article URL -> (image_url, "og"|"html"|"").
_PAGE_IMAGE_CACHE: Dict[str, Tuple[str, str]] = {}
_PAGE_IMAGE_CACHE_MAX = 2048

def _coverage_meta_from_entry(entry: SourceEntry) -> Dict[str, str]:
    """Attach registry coverage to each parsed article for Local mode tiers."""
    return {
        "coverage_city": (entry.city or "").strip(),
        "coverage_province": (entry.province or "").strip(),
        "coverage_level": (entry.coverage_level or "").strip().lower(),
        "feed_registry_key": entry.registry_key,
    }


# General-mode RSS list (national + major regional — see source_registry.include_in_general).
FEEDS: List[Tuple[str, str]] = [
    (e.source_name, e.feed_url) for e in get_general_feed_entries_for_ingest()
]

# Single merged list of feed URLs (CBC, Global, Google News Canada topics, provinces, etc.).
FEED_URLS: List[str] = [e.feed_url for e in get_general_feed_entries_for_ingest()]

# Disabled for now: these URLs often time out, return 404/403, or parse to zero entries
# (blocked bots, paywalls, or layout changes). Re-enable by adding SourceEntry rows.
inactive_feeds: List[Tuple[str, str]] = [
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009"),
    ("National Post", "https://nationalpost.com/feed/"),
    ("Financial Post", "https://financialpost.com/feed/"),
    ("Toronto Star", "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.topstories.rss"),
]

# Backwards compat alias for any code referencing MAX_TOTAL_ARTICLES.
MAX_TOTAL_ARTICLES = MAX_INGEST_ARTICLES

# Log one CBC article per process: feed label vs URL-inferred source (debug)
_CBC_SOURCE_DEBUG_LOGGED = False


def _extract_published(entry) -> (datetime, str):
    """
    Best-effort extraction of a published datetime and display string.
    Falls back to current time if the feed doesn't provide a usable date.
    """
    now = datetime.utcnow()

    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6])
        except Exception:
            dt = now
    else:
        dt = now

    published_text = (entry.get("published") or "").strip()
    if not published_text:
        published_text = dt.strftime("%b %d, %Y %H:%M")

    return dt, published_text


def _looks_like_image_url(url: str) -> bool:
    path = (url or "").lower().split("?", 1)[0]
    return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"))


def _normalize_page_image_url(base: str, raw: str) -> str:
    """Return a full absolute http(s) URL for an image reference."""
    u = (raw or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if base and (base.startswith("http://") or base.startswith("https://")):
        return urljoin(base, u)
    return ""


def _url_from_media_dict(item: dict, base_link: str = "") -> str:
    if not isinstance(item, dict):
        return ""
    u = (item.get("url") or item.get("href") or "").strip()
    if not u:
        return ""
    return _normalize_page_image_url(base_link, u)


def _media_item_pixel_score(item: dict) -> int:
    """Prefer larger declared dimensions (or file size) when picking among RSS media items."""
    if not isinstance(item, dict):
        return 0
    w, h = item.get("width"), item.get("height")
    try:
        wi = int(str(w).replace("px", "").strip()) if w is not None else 0
        hi = int(str(h).replace("px", "").strip()) if h is not None else 0
        if wi > 0 and hi > 0:
            return wi * hi
    except (ValueError, TypeError):
        pass
    for key in ("filesize", "fileSize", "length"):
        v = item.get(key)
        try:
            if v is not None:
                return int(v)
        except (ValueError, TypeError):
            continue
    return 0


def _is_probably_image_media_item(item: dict, url: str) -> bool:
    typ = (item.get("type") or "").lower()
    medium = (item.get("medium") or "").lower()
    return bool(
        typ.startswith("image/")
        or medium == "image"
        or _looks_like_image_url(url)
    )


def _best_media_content_url(entry, base_link: str) -> str:
    """Highest-resolution (or largest) media_content image URL."""
    candidates: List[Tuple[int, int, str]] = []
    for item in entry.get("media_content") or []:
        if not isinstance(item, dict):
            continue
        u = _url_from_media_dict(item, base_link)
        if not u:
            continue
        if not _is_probably_image_media_item(item, u):
            continue
        score = _media_item_pixel_score(item)
        candidates.append((score, len(u), u))
    if not candidates:
        return ""
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]


def _best_enclosure_image_url(entry, base_link: str) -> str:
    """RSS <enclosure> (or media:content-style enclosures) — priority 2 after media:content."""
    for enc in entry.get("enclosures") or []:
        if not isinstance(enc, dict):
            continue
        raw = (enc.get("href") or enc.get("url") or "").strip()
        u = _normalize_page_image_url(base_link, raw)
        if not u:
            continue
        typ = (enc.get("type") or "").lower()
        if typ.startswith("image/") or (not typ and _looks_like_image_url(u)):
            return u
    return ""


def _best_media_thumbnail_url(entry, base_link: str) -> str:
    """Largest media_thumbnail when multiple are present (avoid tiny previews)."""
    candidates: List[Tuple[int, int, str]] = []
    for item in entry.get("media_thumbnail") or []:
        if not isinstance(item, dict):
            continue
        u = _url_from_media_dict(item, base_link)
        if not u:
            continue
        score = _media_item_pixel_score(item)
        candidates.append((score, len(u), u))
    if not candidates:
        return ""
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]


def _img_src_from_html(fragment: str) -> str:
    if not fragment or "<img" not in fragment.lower():
        return ""
    m = re.search(
        r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']',
        fragment,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    u = (m.group(1) or "").strip()
    u = u.replace("&amp;", "&").replace("&#038;", "&")
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return ""


def _image_from_entry_html(entry) -> str:
    """
    Last-resort: first <img src> in RSS summary/content HTML.
    Returns an absolute URL when possible (relative to article link).
    """
    base = (entry.get("link") or "").strip()

    def _first(fragment: str) -> str:
        u = _img_src_from_html(fragment or "")
        return _normalize_page_image_url(base, u) if u else ""

    u = _first(entry.get("summary") or "")
    if u:
        return u
    sd = entry.get("summary_detail")
    if isinstance(sd, dict):
        u = _first(sd.get("value") or "")
        if u:
            return u
    for block in entry.get("content") or []:
        if isinstance(block, dict):
            u = _first(block.get("value") or "")
            if u:
                return u
    return ""


def _extract_rss_structured_image(entry, base_link: str) -> str:
    """
    RSS-only image candidates (no HTTP fetch).
    Order: media:content → enclosure → media_thumbnail → image field → typed image links.
    """
    u = _best_media_content_url(entry, base_link)
    if u:
        return u
    u = _best_enclosure_image_url(entry, base_link)
    if u:
        return u
    u = _best_media_thumbnail_url(entry, base_link)
    if u:
        return u

    img = entry.get("image")
    if isinstance(img, dict):
        raw = (img.get("href") or img.get("url") or "").strip()
        u = _normalize_page_image_url(base_link, raw)
        if u:
            return u
    elif isinstance(img, str) and img.strip():
        u = _normalize_page_image_url(base_link, img.strip())
        if u:
            return u

    for link in entry.get("links") or []:
        if not isinstance(link, dict):
            continue
        typ = (link.get("type") or "").lower()
        if not typ.startswith("image/"):
            continue
        raw = (link.get("href") or link.get("url") or "").strip()
        u = _normalize_page_image_url(base_link, raw)
        if u:
            return u

    return ""


def _best_og_image_from_soup(soup, article_url: str) -> str:
    """
    Some publishers emit multiple og:image tags (sizes). Prefer the largest declared dimensions.
    """
    urls: List[str] = []
    for tag in soup.find_all("meta", property="og:image"):
        c = (tag.get("content") or "").strip()
        if not c:
            continue
        u = _normalize_page_image_url(article_url, c)
        if u:
            urls.append(u)
    if not urls:
        return ""
    if len(urls) == 1:
        return urls[0]

    def _score(u: str) -> Tuple[int, int]:
        """Higher is better: pixel hints in URL path/query, then raw length."""
        low = u.lower()
        score = len(u)
        m = re.search(r"[?&]w=(\d+)", low)
        if m:
            try:
                score += int(m.group(1)) * 10
            except ValueError:
                pass
        if any(x in low for x in ("large", "xlarge", "full", "hero", "wide", "1200", "1600")):
            score += 5000
        if any(x in low for x in ("thumb", "thumbnail", "small", "icon", "avatar")):
            score -= 3000
        return (score, len(u))

    return max(urls, key=_score)


def _normalize_cache_key(article_url: str) -> str:
    u = (article_url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        path = (p.path or "").rstrip("/") or "/"
        return f"{(p.scheme or 'https').lower()}://{(p.netloc or '').lower()}{path.lower()}"
    except Exception:
        return u.lower()


def _is_google_news_bridge_url(url: str) -> bool:
    """True if link likely needs redirect / HTML unwrap to reach the publisher article."""
    u = (url or "").strip().lower()
    if not u:
        return False
    if "news.google.com" in u:
        return True
    if "google.com/url" in u:
        return True
    return False


def _extract_publisher_url_from_google_html(html: bytes) -> str:
    """Last resort: find a non-Google outbound link on a Google News shell page."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    for tag in soup.find_all("link", rel=True):
        rel = tag.get("rel")
        if isinstance(rel, list):
            rel = " ".join(rel)
        if rel and "canonical" in rel.lower():
            href = (tag.get("href") or "").strip()
            if href.startswith("http") and "google." not in urlparse(href).netloc.lower():
                return href
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href.startswith("http"):
            continue
        try:
            host = (urlparse(href).hostname or "").lower()
        except Exception:
            continue
        if not host or "google." in host:
            continue
        if not any(
            x in host for x in ("google.", "gstatic.", "youtube.", "youtu.be")
        ):
            return href
    return ""


def _resolve_publisher_url_for_image(link: str) -> Tuple[str, str]:
    """
    Google News RSS often points at a Google wrapper URL. Follow redirects and,
    if still on Google, try to extract the publisher article URL for og:image.
    Returns (url_to_fetch, resolution_note).
    resolution_note: direct | redirected | canonical | html_extract | failed | empty
    """
    u = (link or "").strip()
    if not u:
        return "", "empty"
    if not _is_google_news_bridge_url(u):
        return u, "direct"
    try:
        r = requests.get(
            u,
            timeout=IMAGE_PAGE_TIMEOUT,
            headers=HTML_PAGE_HEADERS,
            allow_redirects=True,
        )
        r.raise_for_status()
        final = (r.url or u).strip()
        try:
            final_host = (urlparse(final).hostname or "").lower()
        except Exception:
            final_host = ""
        if final != u:
            if "google." not in final_host:
                return final, "redirected"
        if "google." not in final_host:
            return final, "redirected"

        canon = _extract_publisher_url_from_google_html(r.content)
        if canon:
            return canon, "html_extract"

        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup.find_all("link", rel=True):
            rel = tag.get("rel")
            if isinstance(rel, list):
                rel = " ".join(rel)
            if rel and "canonical" in rel.lower():
                href = (tag.get("href") or "").strip()
                if href.startswith("http") and "google." not in (
                    urlparse(href).hostname or ""
                ).lower():
                    return href, "canonical"
        return u, "failed"
    except Exception as e:
        print(f"[fetch_news] resolve_publisher_url_for_image failed: {e!r} link={u[:120]!r}")
        return u, "failed"


_PLACEHOLDER_IMAGE_URLS: Tuple[str, ...] = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    "?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1585829365295-ab7cd400c167"
    "?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e"
    "?auto=format&fit=crop&w=1200&q=60",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa"
    "?auto=format&fit=crop&w=1200&q=60",
)


def _category_placeholder_image_url(article: Dict[str, Any]) -> str:
    """Deterministic placeholder when no article image is available (editorial, not empty)."""
    cat = (article.get("topic_category") or article.get("category") or "").lower()
    src = (article.get("source") or "").lower()
    title = (article.get("title") or "").lower()
    link = (article.get("link") or "").lower()
    h = hashlib.md5(f"{cat}|{src}|{title}|{link}".encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(_PLACEHOLDER_IMAGE_URLS)
    return _PLACEHOLDER_IMAGE_URLS[idx]


def _resolve_ingest_image(
    article: Dict[str, Any], log_prefix: str, idx: int
) -> Tuple[str, str]:
    """
    RSS → resolve Google wrapper → OG on publisher page → RSS html fallback → placeholder.
    Returns (image_url, log_tag): rss | og_final_url | og | html | placeholder | fallback
    """
    link = (article.get("link") or "").strip()
    raw = (article.get("image_url") or "").strip()
    if raw:
        out = _normalize_page_image_url(link, raw) if link else raw
        if _looks_valid_http_url(out):
            return out, "rss"
        raw = ""

    if link:
        resolved, res_note = _resolve_publisher_url_for_image(link)
        fetch_url = resolved or link
        cache_key = _normalize_cache_key(fetch_url)
        if cache_key and cache_key in _PAGE_IMAGE_CACHE:
            page_u, page_kind = _PAGE_IMAGE_CACHE[cache_key]
        else:
            page_u, page_kind = _fetch_page_image_via_http(fetch_url)
            if cache_key:
                _page_cache_evict_if_needed()
                _PAGE_IMAGE_CACHE[cache_key] = (page_u, page_kind)
        if page_u:
            if res_note in ("redirected", "canonical", "html_extract"):
                tag = "og_final_url"
            else:
                tag = page_kind if page_kind in ("og", "html") else "og"
            out = _normalize_page_image_url(fetch_url, page_u)
            return out, tag
        print(
            f"[fetch_news] [{log_prefix}] image_resolve_failed resolution={res_note} "
            f"idx={idx} link={link[:100]!r} fetch_url={fetch_url[:100]!r}"
        )

    raw = (article.get("_image_html_fallback") or "").strip()
    if raw:
        out = _normalize_page_image_url(link, raw) if link else raw
        if _looks_valid_http_url(out):
            return out, "html"

    ph = _category_placeholder_image_url(article)
    return ph, "placeholder"


def _page_cache_evict_if_needed() -> None:
    while len(_PAGE_IMAGE_CACHE) >= _PAGE_IMAGE_CACHE_MAX:
        _PAGE_IMAGE_CACHE.pop(next(iter(_PAGE_IMAGE_CACHE)))


def _extract_images_from_page_soup(
    soup: BeautifulSoup, article_url: str
) -> Tuple[str, str]:
    """
    Return (image_url, image_source) where image_source is 'og' or 'html'.
    Priority: og:image (and twitter/link rel) → first meaningful <img> in body.
    """
    u = _best_og_image_from_soup(soup, article_url)
    if u:
        return (u, "og")

    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if not tag:
        tag = soup.find("meta", property="twitter:image")
    if tag and tag.get("content"):
        u = _normalize_page_image_url(article_url, tag["content"])
        if u:
            return (u, "og")

    for link in soup.find_all("link", rel=True):
        rel = link.get("rel")
        if isinstance(rel, list):
            rel = " ".join(rel)
        if not rel or "image_src" not in rel.lower():
            continue
        href = (link.get("href") or "").strip()
        if href:
            u = _normalize_page_image_url(article_url, href)
            if u:
                return (u, "og")

    for img in soup.find_all("img"):
        src = (
            (img.get("src") or img.get("data-src") or img.get("data-lazy-src") or "")
            .strip()
        )
        if not src or src.startswith("data:"):
            continue
        w, h = img.get("width"), img.get("height")
        if w is not None and h is not None:
            try:
                wi = int(str(w).replace("px", "").strip())
                hi = int(str(h).replace("px", "").strip())
                if wi < 80 and hi < 80:
                    continue
            except ValueError:
                pass
        u = _normalize_page_image_url(article_url, src)
        if u:
            return (u, "html")

    return ("", "")


def _fetch_page_image_via_http(
    article_url: str, timeout: float = IMAGE_PAGE_TIMEOUT
) -> Tuple[str, str]:
    """One HTTP GET; parse HTML for og/twitter/body img. Returns (url, og|html|empty)."""
    if not article_url or not (
        article_url.startswith("http://") or article_url.startswith("https://")
    ):
        return ("", "")
    try:
        resp = requests.get(
            article_url, timeout=timeout, headers=HTML_PAGE_HEADERS
        )
        resp.raise_for_status()
    except Exception:
        return ("", "")

    try:
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return ("", "")

    return _extract_images_from_page_soup(soup, article_url)


def _cached_page_image_for_link(link: str) -> Tuple[str, str]:
    """Cached fetch; returns (url, 'og'|'html') or ('', '') if unresolved."""
    key = _normalize_cache_key(link)
    if not key:
        return ("", "")
    if key in _PAGE_IMAGE_CACHE:
        return _PAGE_IMAGE_CACHE[key]
    u, src = _fetch_page_image_via_http(link)
    _page_cache_evict_if_needed()
    _PAGE_IMAGE_CACHE[key] = (u, src)
    return (u, src)


def _publisher_site_fallback_url(link: str) -> str:
    """Favicon from article hostname (publisher-specific). Always https."""
    try:
        netloc = urlparse((link or "").strip()).netloc
        if netloc:
            return f"https://www.google.com/s2/favicons?domain={netloc}&sz=256"
    except Exception:
        pass
    return GLOBAL_FALLBACK_IMAGE_URL


def _looks_valid_http_url(url: str) -> bool:
    u = (url or "").strip()
    return u.startswith("http://") or u.startswith("https://")


def _extract_image_from_article_page(
    article_url: str, timeout: float = IMAGE_PAGE_TIMEOUT
) -> str:
    """Backward compat: return URL only (used by tests or callers)."""
    u, _ = _fetch_page_image_via_http(article_url, timeout=timeout)
    return u


def _entry_text_for_summary(entry) -> str:
    """
    Best-effort article text from RSS fields.
    We prefer richer body text, then fallback to short summary fields.
    """
    content_items = entry.get("content") or []
    if isinstance(content_items, list):
        for c in content_items:
            if isinstance(c, dict):
                v = (c.get("value") or "").strip()
                if v:
                    return BeautifulSoup(v, "html.parser").get_text(" ", strip=True)

    for key in ("summary", "description"):
        v = (entry.get(key) or "").strip()
        if v:
            return BeautifulSoup(v, "html.parser").get_text(" ", strip=True)

    return ""


def infer_region(title: str, summary: str = "") -> str:
    """
    Rules-based region: city → province/territory → Canada → World.
    Cities are checked before provinces so Toronto beats Ontario, etc.
    """
    text = f"{title} {summary}"[:2000].lower()

    def matches(words):
        return any(w in text for w in words)

    # --- Major cities (before broad province keywords) ---
    if matches(["ottawa", "gatineau"]):
        return "Ottawa"
    if matches(
        [
            "toronto",
            "gta",
            "mississauga",
            "brampton",
            "durham region",
            "markham",
            "vaughan",
            "peel region",
        ]
    ):
        return "Toronto"
    if matches(["montreal", "montréal", "laval"]):
        return "Montreal"
    if matches(["vancouver", "surrey", "burnaby", "new westminster"]):
        return "Vancouver"
    if matches(["calgary"]):
        return "Calgary"
    if matches(["edmonton"]):
        return "Edmonton"
    if matches(["winnipeg"]):
        return "Winnipeg"
    if matches(["halifax", "dartmouth"]):
        return "Halifax"
    if matches(["regina"]):
        return "Regina"
    if matches(["saskatoon"]):
        return "Saskatoon"

    # --- Provinces & territories ---
    if matches(["ontario", "doug ford", "ford government"]):
        return "Ontario"
    if matches(["quebec", "québec", "legault"]):
        return "Quebec"
    if matches(["alberta", "red deer", "medicine hat"]):
        return "Alberta"
    if matches(["british columbia", "b.c.", "victoria bc", "kelowna", "kamloops"]):
        return "British Columbia"
    if matches(["manitoba", "brandon manitoba"]):
        return "Manitoba"
    if matches(["saskatchewan"]):
        return "Saskatchewan"
    if matches(["nova scotia", "cape breton"]):
        return "Nova Scotia"
    if matches(["fredericton", "moncton", "new brunswick", "saint john n.b"]):
        return "New Brunswick"
    if matches(["charlottetown", "p.e.i.", "pei ", "prince edward island"]):
        return "Prince Edward Island"
    if matches(["st. john's", "st johns", "newfoundland", "labrador"]):
        return "Newfoundland and Labrador"
    if matches(["whitehorse", "yukon"]):
        return "Yukon"
    if matches(["yellowknife", "northwest territories"]):
        return "Northwest Territories"
    if matches(["iqaluit", "nunavut"]):
        return "Nunavut"

    # --- Clear international context (drop at ingest via is_canadian_article) ---
    if matches(
        [
            "u.s.",
            "united states",
            "trump",
            "white house",
            "iran",
            "iraq",
            "nato",
            "china",
            "europe",
            "ukraine",
            "israel",
            "gaza",
            "russia",
            "kremlin",
        ]
    ):
        return "World"

    # --- National / ambiguous (Canadian RSS → prefer Canada over vague Other) ---
    if matches(["canada", "canadian", "federal", "parliament", "ottawa parliament"]):
        return "Canada"
    return "Canada"


# Regions produced by infer_region() that we treat as Canadian for ingestion.
CANADIAN_REGIONS = frozenset(
    {
        "Canada",
        "Ottawa",
        "Toronto",
        "Montreal",
        "Vancouver",
        "Calgary",
        "Edmonton",
        "Winnipeg",
        "Halifax",
        "Regina",
        "Saskatoon",
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


# Drop known international outlets even if region was mis-inferred as empty.
_BLOCKED_FOREIGN_NEWS_HOSTS = (
    "theguardian.com",
    "bbc.co.uk",
    "bbc.com",
    "reuters.com",
    "nytimes.com",
    "washingtonpost.com",
    "cnn.com",
    "aljazeera.com",
    "dw.com",
    "france24.com",
    "ft.com",
    "economist.com",
)


def _is_blocked_foreign_news_domain(link: str) -> bool:
    try:
        host = (urlparse(link).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    for h in _BLOCKED_FOREIGN_NEWS_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    return False


def _canadian_news_domain(link: str) -> bool:
    """
    True if the story URL is hosted on a known Canadian news site or .ca domain.
    Used only when region is empty (not World/Other — those are dropped first).
    """
    try:
        host = (urlparse(link).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if _is_blocked_foreign_news_domain(link):
        return False
    if host.endswith(".ca"):
        return True
    # Major Canadian news hosts (not exhaustive; .ca catches most)
    canadian_hosts = (
        "cbc.ca",
        "globalnews.ca",
        "ctvnews.ca",
        "thestar.com",
        "nationalpost.com",
        "financialpost.com",
        "torontosun.com",
        "vancouversun.com",
        "calgaryherald.com",
        "leaderpost.com",
        "montrealgazette.com",
        "edmontonjournal.com",
        "ottawacitizen.com",
    )
    for suffix in canadian_hosts:
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def is_canadian_article(article: Dict) -> bool:
    """
    Canada Brief: keep Canada/province/territory/city rows, or .ca / known CA hosts
    when region is empty. Drop World; block obvious foreign URLs.
    """
    r = (article.get("region") or "").strip()
    if r == "World":
        return False
    if r in CANADIAN_REGIONS:
        return True
    link = (article.get("link") or "").strip()
    if _is_blocked_foreign_news_domain(link):
        return False
    if not r:
        return _canadian_news_domain(link)
    return False


def strip_tracking_params(url: str) -> str:
    """
    Remove common tracking query params (utm_*, fbclid, …) before link comparison.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw)
        if not p.netloc:
            return raw
        pairs = parse_qsl(p.query, keep_blank_values=True)
        keep: List[Tuple[str, str]] = []
        for k, v in pairs:
            lk = k.lower()
            if lk.startswith("utm_"):
                continue
            if lk in (
                "fbclid",
                "gclid",
                "mc_eid",
                "igshid",
                "_ga",
                "mkt_tok",
            ):
                continue
            keep.append((k, v))
        new_query = urlencode(keep, doseq=True)
        # Drop fragment; normalize netloc casing for consistency before lower in normalize_link.
        return urlunparse(
            (p.scheme, p.netloc.lower(), p.path or "", p.params, new_query, "")
        )
    except Exception:
        return raw


def normalize_link(link: str) -> str:
    cleaned = strip_tracking_params((link or "").strip()).lower()
    while cleaned.endswith("/") and len(cleaned) > 1:
        cleaned = cleaned[:-1]
    return cleaned


def normalize_title_for_dedup(title: str) -> str:
    t = (title or "").strip().lower()
    t = t.replace("–", " ").replace("—", " ").replace("-", " ")
    t = re.sub(r"[^\w\s]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def content_fingerprint_for_dedup(article: Dict[str, Any]) -> str:
    """
    Stable secondary key: hash(normalized_title + source + published).
    Catches duplicate stories when URLs differ (syndication, redirects, campaign params).
    """
    t = normalize_title_for_dedup(article.get("title") or "")
    src = (article.get("source") or "").strip().lower()
    pub = (article.get("published") or "").strip().lower()
    raw = f"{t}|{src}|{pub}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def specific_source_label(raw: str) -> str:
    """
    Specific feed / edition label (what readers see as `source`).
    Preserves regional and section detail: CBC Manitoba, Global News Ottawa, etc.
    Does not replace them with a generic publisher name.
    """
    s = (raw or "").strip()
    if not s:
        return "Unknown"
    # "Global News - Ottawa" → "Global News Ottawa" (keep detail, drop dash)
    if " - " in s:
        left, right = s.split(" - ", 1)
        return f"{left.strip()} {right.strip()}".strip()
    return s


def infer_source_group(source: str) -> str:
    """
    Broader publisher / network for grouping (`source_group`), inferred from `source`.
    """
    s = (source or "").strip()
    if not s:
        return "Unknown"
    lower = s.lower()

    if lower.startswith("cbc"):
        return "CBC"
    if lower.startswith("google news") or "google news" in lower:
        return "Google News"
    if lower.startswith("global news"):
        return "Global News"
    if "reuters" in lower:
        return "Reuters"
    if lower.startswith("bbc"):
        return "BBC"
    if "guardian" in lower:
        return "The Guardian"
    if lower.startswith("ctv"):
        return "CTV News"
    if "national post" in lower:
        return "National Post"
    if "toronto star" in lower or lower.startswith("the star"):
        return "Toronto Star"
    if "financial post" in lower:
        return "Financial Post"

    # Fallback: treat the specific label as its own group
    return s


def normalize_source_name(raw: str) -> str:
    """Backward-compatible alias: same as specific_source_label."""
    return specific_source_label(raw)


def infer_cbc_source_from_url(link: str, feed_label: str) -> str:
    """
    CBC: the article URL often reflects the real region or desk better than the RSS feed.

    If the link matches a known path, return that label; otherwise keep the feed label.
    """
    if not link:
        return feed_label
    low = link.lower()
    if "cbc.ca" not in low:
        return feed_label

    # Order matters: check specific regional paths before generic sections.
    if "/canada/saskatchewan/" in low:
        return "CBC Saskatchewan"
    if "/canada/manitoba/" in low:
        return "CBC Manitoba"
    if "/canada/toronto/" in low:
        return "CBC Toronto"
    if "/canada/montreal/" in low:
        return "CBC Montreal"
    if "/news/entertainment/" in low:
        return "CBC News"
    return feed_label


def refine_article_source(link: str, feed_label: str) -> str:
    """
    Article-level source: start from the feed name, then refine using the story URL.

    Global News feeds already use clear names (e.g. Global News Ottawa); we keep those.
    """
    label = infer_cbc_source_from_url(link, feed_label)
    return label


def _maybe_log_cbc_source_debug(
    feed_label: str, inferred_source: str, source_group: str, link: str
) -> None:
    """Print once: original feed source, inferred source, and source_group for a CBC URL."""
    global _CBC_SOURCE_DEBUG_LOGGED
    if _CBC_SOURCE_DEBUG_LOGGED:
        return
    if "cbc.ca" not in (link or "").lower():
        return
    _CBC_SOURCE_DEBUG_LOGGED = True
    print(
        "[fetch_news] CBC source debug (one article): "
        f"original_feed={feed_label!r} inferred_source={inferred_source!r} "
        f"source_group={source_group!r} link={link[:120]!r}"
    )


def _parse_feed_response(
    source_name: str,
    _feed_url: str,
    content: bytes,
    coverage: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    """Turn RSS/Atom bytes into article dicts (no HTTP)."""
    feed = feedparser.parse(content)
    raw_entries = getattr(feed, "entries", []) or []
    raw_count = len(raw_entries)
    print(
        f"[fetch_news] {source_name}: parsed_entries={raw_count} (raw RSS entries)"
    )

    items: List[Dict] = []
    for entry in raw_entries:
        try:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not link:
                continue

            published_dt, published_str = _extract_published(entry)
            headline = title or link
            article_text = _entry_text_for_summary(entry)
            # Summary filled once after clustering in ingest (deterministic; no AI).
            summary = ""
            region = infer_region(headline, article_text)
            # RSS structured media first; HTML summary + article-page og:image applied in fetch_all_feeds.
            base_link = link
            rss_image = _extract_rss_structured_image(entry, base_link)
            html_fallback_image = _image_from_entry_html(entry) or ""
            image_url = rss_image or ""

            feed_label = specific_source_label(source_name)
            label = refine_article_source(link, feed_label)
            source_group = infer_source_group(label)
            if label.lower().startswith("cbc"):
                source_group = "CBC"

            _maybe_log_cbc_source_debug(feed_label, label, source_group, link)

            cov = coverage or {}
            article = {
                "title": title or link,
                "summary": summary,
                "summary_status": "pending",
                "source": label,
                "source_group": source_group,
                "link": link,
                "published": published_str,
                "region": region,
                "coverage_city": (cov.get("coverage_city") or "").strip(),
                "coverage_province": (cov.get("coverage_province") or "").strip(),
                "coverage_level": (cov.get("coverage_level") or "").strip(),
                "feed_registry_key": (cov.get("feed_registry_key") or "").strip(),
                "image_url": image_url,
                # Used only during ingest if RSS + og:image are empty; stripped before DB save.
                "_image_html_fallback": html_fallback_image,
                "published_raw": published_dt,
                # Kept for DB rss_excerpt + deterministic summary at ingest; trimmed at save.
                "rss_excerpt": (article_text or "")[:12000],
            }
            topic = assign_topic_category(article)
            article["topic_category"] = topic
            article["category"] = topic
            items.append(article)
        except Exception:
            continue

    valid_count = len(items)
    print(f"[fetch_news] {source_name}: valid_articles_added={valid_count}")
    return items


def fetch_feed(source_name: str, url: str) -> List[Dict]:
    """
    Fetch and parse a single RSS feed and return a list of normalized article dicts.
    Each article includes:
      title, summary, source, link, published, category, topic_category, region, image_url
    """
    print(f"[fetch_news] Fetching {source_name} ({url})")
    t_req_start = time.time()
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers=HTTP_HEADERS
        )
        elapsed = time.time() - t_req_start
        status_code = resp.status_code
        print(f"[fetch_news] {source_name}: status={status_code}, time={elapsed:.3f}s")
        resp.raise_for_status()
    except Exception as e:
        print(f"[fetch_news] {source_name}: skipped due to error: {e}")
        return []

    return _parse_feed_response(source_name, url, resp.content, None)


def _fetch_single_registry_feed(
    entry: SourceEntry,
    log_prefix: str,
) -> Dict[str, Any]:
    """
    Sync: HTTP GET + parse one registry feed.
    Returns dict: ok, entry, items, error, stage, elapsed_s.
    """
    source_name = entry.source_name
    feed_url = entry.feed_url
    cov = _coverage_meta_from_entry(entry)
    t_req_start = time.time()
    try:
        print(
            f"[fetch_news] [{log_prefix}] Fetching {source_name} ({feed_url}) "
            f"[registry={entry.registry_key} level={entry.coverage_level}]"
        )
        response = requests.get(
            feed_url, timeout=REQUEST_TIMEOUT, headers=HTTP_HEADERS
        )
        elapsed = time.time() - t_req_start
        print(
            f"[fetch_news] [{log_prefix}] {source_name}: status={response.status_code}, "
            f"time={elapsed:.3f}s"
        )
        response.raise_for_status()
    except Exception as e:
        print(f"[fetch_news] [{log_prefix}] {source_name}: skipped due to error: {e}")
        return {
            "ok": False,
            "entry": entry,
            "items": [],
            "error": str(e),
            "stage": "http",
            "elapsed_s": time.time() - t_req_start,
        }

    try:
        items = _parse_feed_response(
            source_name, feed_url, response.content, cov
        )
        return {
            "ok": True,
            "entry": entry,
            "items": items,
            "error": None,
            "stage": None,
            "elapsed_s": time.time() - t_req_start,
        }
    except Exception as e:
        print(f"[fetch_news] [{log_prefix}] {source_name}: skipped due to error: {e}")
        return {
            "ok": False,
            "entry": entry,
            "items": [],
            "error": str(e),
            "stage": "parse",
            "elapsed_s": time.time() - t_req_start,
        }


async def _gather_feeds_parallel(
    entries: List[SourceEntry], log_prefix: str
) -> List[Dict[str, Any]]:
    """Fetch all feeds concurrently; one feed failure does not cancel others."""

    async def fetch_one(entry: SourceEntry) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_fetch_single_registry_feed, entry, log_prefix),
                timeout=FEED_FETCH_ASYNC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            print(
                f"[fetch_news] [{log_prefix}] {entry.source_name}: "
                f"skipped due to async timeout ({FEED_FETCH_ASYNC_TIMEOUT_SEC:.1f}s)"
            )
            return {
                "ok": False,
                "entry": entry,
                "items": [],
                "error": f"async_timeout>{FEED_FETCH_ASYNC_TIMEOUT_SEC:.0f}s",
                "stage": "async_timeout",
                "elapsed_s": FEED_FETCH_ASYNC_TIMEOUT_SEC,
            }
        except Exception as e:
            print(
                f"[fetch_news] [{log_prefix}] {entry.source_name}: "
                f"skipped due to wrapper error: {e}"
            )
            return {
                "ok": False,
                "entry": entry,
                "items": [],
                "error": str(e),
                "stage": "async_wrap",
                "elapsed_s": 0.0,
            }

    return await asyncio.gather(*[fetch_one(e) for e in entries])


def _run_parallel_feed_fetch(
    entries: List[SourceEntry], log_prefix: str, diag: Dict[str, Any]
) -> List[Dict]:
    """
    Run parallel fetch using asyncio.gather (each feed in a thread via asyncio.to_thread).
    Uses asyncio.run() — safe when called from sync ingest/refresh (no running loop).
    Falls back to sequential fetch if a loop is already running or asyncio.run fails.
    """
    results: List[Dict[str, Any]]
    try:
        results = asyncio.run(_gather_feeds_parallel(entries, log_prefix))
    except RuntimeError as e:
        print(
            f"[fetch_news] [{log_prefix}] parallel fetch unavailable ({e!r}); "
            f"falling back to sequential feed fetch"
        )
        results = []
        for entry in entries:
            results.append(_fetch_single_registry_feed(entry, log_prefix))
    all_items: List[Dict] = []
    for res in results:
        entry = res["entry"]
        if res.get("ok"):
            all_items.extend(res["items"])
            diag["feeds_fetched_ok"] += 1
        else:
            diag["feeds_fetch_failed"] += 1
            if len(diag["failed_feed_samples"]) < 12:
                diag["failed_feed_samples"].append(
                    {
                        "registry_key": entry.registry_key,
                        "feed_url": entry.feed_url,
                        "stage": res.get("stage") or "unknown",
                        "error": (res.get("error") or "")[:200],
                    }
                )
    return all_items


def _ingest_pipeline_from_entries(
    entries: List[SourceEntry],
    *,
    log_prefix: str,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Shared fetch → dedupe → Canadian filter → cap → image pass for any SourceEntry list.

    `log_prefix` is "general" or "local" for log lines only.
    Returns (articles, diagnostics) for merge/ops visibility.
    """
    global _CBC_SOURCE_DEBUG_LOGGED
    _CBC_SOURCE_DEBUG_LOGGED = False

    diag: Dict[str, Any] = {
        "feeds_requested": len(entries),
        "feeds_fetched_ok": 0,
        "feeds_fetch_failed": 0,
        "failed_feed_samples": [],
        "raw_entries": 0,
        "pipeline_skipped_duplicate_link": 0,
        "pipeline_skipped_duplicate_title": 0,
        "pipeline_skipped_duplicate_content_hash": 0,
        "sample_pipeline_skipped_links": [],
        "sample_pipeline_skipped_titles": [],
        "sample_pipeline_skipped_content_hash": [],
    }
    _SAMPLE_CAP = 5

    rs = registry_stats()
    print(
        f"[fetch_news] [{log_prefix}] registry_bootstrap "
        f"entries_defined={rs['entries_defined']} entries_active={rs['entries_active']} "
        f"active_general_pool={rs['entries_active_general_pool']} "
        f"feeds_selected_this_run={len(entries)}"
    )
    print(
        f"[fetch_news] [{log_prefix}] selected_registry_keys="
        f"{[e.registry_key for e in entries]}"
    )

    t_total_start = time.time()
    all_items: List[Dict] = []

    t_feed_start = time.time()
    all_items = _run_parallel_feed_fetch(entries, log_prefix, diag)
    feed_fetch_s = time.time() - t_feed_start
    print(
        f"[fetch_news] [{log_prefix}] SUCCESSFUL SOURCES:",
        list(set(a["source"] for a in all_items if a.get("source"))),
    )

    tier_raw = Counter()
    for a in all_items:
        cl = (a.get("coverage_level") or "").strip().lower()
        if cl in ("city", "civic"):
            tier_raw["city"] += 1
        elif cl == "province":
            tier_raw["province"] += 1
        elif cl == "national":
            tier_raw["national"] += 1
        else:
            tier_raw["unknown"] += 1
    print(
        f"[fetch_news] [{log_prefix}] raw_articles_parsed_by_tier "
        f"{dict(sorted(tier_raw.items(), key=lambda x: x[0]))} total_raw={len(all_items)}"
    )

    raw_by_key = Counter()
    for a in all_items:
        k = (a.get("feed_registry_key") or "").strip() or "unknown"
        raw_by_key[k] += 1
    print(
        f"[fetch_news] [{log_prefix}] raw_articles_per_registry_key="
        f"{dict(sorted(raw_by_key.items(), key=lambda x: x[0]))}"
    )

    combined_count_before_dedupe = len(all_items)
    diag["raw_entries"] = combined_count_before_dedupe
    sources_before_dedupe = sorted(
        {a.get("source", "") for a in all_items if a.get("source")}
    )
    print(f"[fetch_news] [{log_prefix}] combined_count_before_dedupe={combined_count_before_dedupe}")
    print(f"[fetch_news] [{log_prefix}] sources_before_dedupe={sources_before_dedupe}")

    t_dedupe_start = time.time()
    # Dedupe: normalized link (tracking params stripped) OR content fingerprint
    # (title + source + published). Avoids aggressive title-only drops across outlets.
    seen_links = set()
    seen_content_hashes = set()
    deduped: List[Dict] = []

    for item in all_items:
        norm_link = normalize_link(item.get("link", ""))
        fp = content_fingerprint_for_dedup(item)

        if norm_link and norm_link in seen_links:
            diag["pipeline_skipped_duplicate_link"] += 1
            if len(diag["sample_pipeline_skipped_links"]) < _SAMPLE_CAP:
                diag["sample_pipeline_skipped_links"].append(
                    {
                        "reason": "duplicate_normalized_link",
                        "normalized_link": norm_link[:220],
                        "title": (item.get("title") or "")[:120],
                    }
                )
            continue
        if fp in seen_content_hashes:
            diag["pipeline_skipped_duplicate_content_hash"] += 1
            if len(diag["sample_pipeline_skipped_content_hash"]) < _SAMPLE_CAP:
                diag["sample_pipeline_skipped_content_hash"].append(
                    {
                        "reason": "duplicate_content_fingerprint",
                        "fingerprint": fp,
                        "title": (item.get("title") or "")[:120],
                        "source": (item.get("source") or "")[:80],
                    }
                )
            continue

        deduped.append(item)
        if norm_link:
            seen_links.add(norm_link)
        seen_content_hashes.add(fp)

    x = combined_count_before_dedupe
    y = len(deduped)
    print(f"[fetch_news] [{log_prefix}] deduplicated from {x} to {y} articles")
    sources_after_dedupe = sorted(
        {a.get("source", "") for a in deduped if a.get("source")}
    )
    print(f"[fetch_news] [{log_prefix}] sources_after_dedupe={sources_after_dedupe}")

    deduped.sort(
        key=lambda item: item.get("published_raw", datetime.utcnow()),
        reverse=True,
    )

    total_after_dedupe = len(deduped)
    canadian_deduped = [a for a in deduped if is_canadian_article(a)]
    removed_non_canadian = total_after_dedupe - len(canadian_deduped)
    sources_kept = sorted(
        {a.get("source", "") for a in canadian_deduped if a.get("source")}
    )
    print(
        f"[fetch_news] [{log_prefix}] canadian_filter: "
        f"total_fetched_raw={combined_count_before_dedupe} "
        f"after_dedupe={total_after_dedupe} "
        f"canadian_kept={len(canadian_deduped)} "
        f"filtered_out_non_canadian={removed_non_canadian}"
    )
    print(f"[fetch_news] [{log_prefix}] sources_kept_after_canadian_filter={sources_kept}")

    kept_by_key = Counter()
    for a in canadian_deduped:
        k = (a.get("feed_registry_key") or "").strip() or "unknown"
        kept_by_key[k] += 1
    print(
        f"[fetch_news] [{log_prefix}] stories_kept_after_canadian_filter_by_registry_key="
        f"{dict(sorted(kept_by_key.items(), key=lambda x: x[0]))}"
    )

    limited = canadian_deduped[:MAX_INGEST_ARTICLES]
    dedupe_s = time.time() - t_dedupe_start
    diag["after_pipeline_dedupe"] = len(deduped)
    diag["after_canadian_filter"] = len(canadian_deduped)
    diag["filtered_non_canadian"] = removed_non_canadian

    ingest_cov = Counter()
    for a in limited:
        cl = (a.get("coverage_level") or "").strip().lower()
        ingest_cov[cl if cl else "legacy"] += 1
    print(
        f"[fetch_news] [{log_prefix}] ingest_stories_by_coverage_level "
        f"{dict(sorted(ingest_cov.items(), key=lambda x: x[0]))} "
        f"total_in_ingest_batch={len(limited)}"
    )

    t_image_start = time.time()
    image_source_counts: Counter[str] = Counter()
    seen_image_urls: set[str] = set()
    for idx, article in enumerate(limited):
        link = (article.get("link") or "").strip()
        raw = (article.get("image_url") or "").strip()
        image_source = "feed"

        if not _looks_valid_http_url(raw):
            if idx < max(0, MAX_SYNC_IMAGE_ENRICH_PER_INGEST):
                raw, image_source = _resolve_ingest_image(article, log_prefix, idx)
            else:
                raw = _category_placeholder_image_url(article)
                image_source = "placeholder_deferred"

        if not _looks_valid_http_url(raw):
            raw = _category_placeholder_image_url(article)
            image_source = "placeholder"

        # Avoid visually repetitive feeds when many rows resolve to the same image URL.
        norm_img = (raw or "").strip().lower()
        if norm_img and norm_img in seen_image_urls:
            raw = _category_placeholder_image_url(article)
            image_source = "placeholder_duplicate_image"
            norm_img = raw.lower()
        if norm_img:
            seen_image_urls.add(norm_img)

        article.pop("_image_html_fallback", None)
        article["image_url"] = raw
        image_source_counts[image_source] += 1
        print(
            f"[fetch_news] [{log_prefix}] image_final image_source={image_source} "
            f"idx={idx} link={link[:100]!r} url={raw[:140]!r}"
        )
    image_s = time.time() - t_image_start
    print(
        f"[fetch_news] [{log_prefix}] image_source_counts "
        f"{dict(sorted(image_source_counts.items(), key=lambda x: x[0]))}"
    )

    trimmed: List[Dict] = []
    for item in limited:
        trimmed.append(dict(item))

    total_s = time.time() - t_total_start
    print(
        f"[fetch_news] [{log_prefix}] timing: feed_fetch={feed_fetch_s:.3f}s "
        f"dedupe_sort_cap={dedupe_s:.3f}s "
        f"image_scrape={image_s:.3f}s total_pipeline_s={total_s:.3f}s "
        f"(clustering + lazy summaries in API /news)"
    )

    diag["candidates"] = len(trimmed)
    diag["feeds_fetched"] = diag["feeds_fetched_ok"]
    diag["skipped_duplicates"] = (
        diag["pipeline_skipped_duplicate_link"]
        + diag["pipeline_skipped_duplicate_content_hash"]
    )
    diag["ingestion_time_seconds"] = round(total_s, 4)
    print(
        f"[fetch_news] [{log_prefix}] [ingest_diag] feeds_requested={diag['feeds_requested']} "
        f"feeds_fetched={diag['feeds_fetched']} feeds_fetched_ok={diag['feeds_fetched_ok']} "
        f"feeds_fetch_failed={diag['feeds_fetch_failed']} "
        f"raw_entries={diag['raw_entries']} candidates={diag['candidates']} "
        f"skipped_duplicates={diag['skipped_duplicates']} "
        f"(link={diag['pipeline_skipped_duplicate_link']} "
        f"content_hash={diag['pipeline_skipped_duplicate_content_hash']}) "
        f"ingestion_time_seconds={diag['ingestion_time_seconds']}"
    )

    return trimmed, diag


def fetch_general_feeds() -> List[Dict]:
    """
    General mode: national + major regional feeds (include_in_general). Stored in `news`.
    """
    ge = get_general_feed_entries_for_ingest()
    print(
        f"[fetch_news] general_mode: using {len(ge)} sources "
        f"(national + regional anchors from registry)"
    )
    items, _diag = _ingest_pipeline_from_entries(ge, log_prefix="general")
    return items


def fetch_general_feeds_with_diagnostics() -> Tuple[List[Dict], Dict[str, Any]]:
    """Same as fetch_general_feeds plus a diagnostics dict (merge ingest / POST /ingest/run)."""
    ge = get_general_feed_entries_for_ingest()
    print(
        f"[fetch_news] general_mode: using {len(ge)} sources "
        f"(national + regional anchors from registry)"
    )
    return _ingest_pipeline_from_entries(ge, log_prefix="general")


def fetch_local_feeds(city: str, province: str) -> List[Dict]:
    """
    Local mode: registry-scoped city → province → national for one location (local_source_config).
    Stored in `news_local` — never mixed with General ingest.
    """
    c = (city or "").strip()
    p = (province or "").strip()
    plan = build_local_feed_plan(c, p)
    entries = plan.entries
    _, meta = describe_local_feed_plan(c, p, plan=plan)
    print(
        f"[fetch_news] local_ingest_plan city={c!r} province={p!r} "
        f"feed_count={len(entries)} slug_patterns={meta}"
    )
    print(
        f"[fetch_news] local_mode: selected_sources={len(entries)} "
        f"keys={[e.registry_key for e in entries]}"
    )
    for e in entries:
        print(
            f"[fetch_news] local_feed_selected registry_key={e.registry_key!r} "
            f"level={e.coverage_level!r} url={e.feed_url!r}"
        )
    items, _diag = _ingest_pipeline_from_entries(entries, log_prefix="local")
    return items


def fetch_all_feeds() -> List[Dict]:
    """Backward-compatible alias for General-mode ingest."""
    return fetch_general_feeds()
