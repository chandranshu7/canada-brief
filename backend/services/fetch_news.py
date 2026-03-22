"""
services/fetch_news.py

Fetches articles from Canadian RSS feeds using requests + feedparser and
returns ready-to-save article dicts, including a fast local summary.
"""

import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from services.summarize import normalize_stored_summary

# Feed RSS fetch: keep tight so one slow host does not block the whole refresh.
REQUEST_TIMEOUT = 5

# Article page fetch (og:image only): separate, slightly shorter timeout.
IMAGE_PAGE_TIMEOUT = 4

# After dedupe + sort, cap how many stories we ingest (cluster + store). No bulk AI here.
MAX_INGEST_ARTICLES = 150

# Only the newest N articles may trigger an extra HTTP request to find a hero image.
IMAGE_SCRAPE_MAX_ARTICLES = 8

# Browser-like headers reduce 403/blocked responses from some CDNs and news sites.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
}

canadian_feeds: List[Tuple[str, str]] = [
    ("Global News - Top Stories", "https://globalnews.ca/feed/"),
    ("Global News - Canada", "https://globalnews.ca/canada/feed/"),
    ("Global News - Ottawa", "https://globalnews.ca/ottawa/feed/"),
    ("Global News - Politics", "https://globalnews.ca/politics/feed/"),
    ("CBC News", "https://www.cbc.ca/webfeed/rss/rss-topstories"),
    ("CBC Toronto", "https://www.cbc.ca/webfeed/rss/rss-canada-toronto"),
    ("CBC Montreal", "https://www.cbc.ca/webfeed/rss/rss-canada-montreal"),
    ("CBC Manitoba", "https://www.cbc.ca/webfeed/rss/rss-canada-manitoba"),
]

world_feeds: List[Tuple[str, str]] = [
    ("BBC", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Reuters World", "https://feeds.reuters.com/Reuters/worldNews"),
    ("The Guardian World", "https://www.theguardian.com/world/rss"),
]

# Disabled for now: these URLs often time out, return 404/403, or parse to zero entries
# (blocked bots, paywalls, or layout changes). Re-enable when you verify they work again.
inactive_feeds: List[Tuple[str, str]] = [
    ("CTV News", "https://www.ctvnews.ca/rss/ctvnews-ca-top-stories-public-rss-1.822009"),
    ("National Post", "https://nationalpost.com/feed/"),
    ("Financial Post", "https://financialpost.com/feed/"),
    ("Toronto Star", "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.topstories.rss"),
]

FEEDS: List[Tuple[str, str]] = canadian_feeds + world_feeds

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


def _url_from_media_dict(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    u = (item.get("url") or item.get("href") or "").strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return ""


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
    u = _img_src_from_html(entry.get("summary") or "")
    if u:
        return u
    sd = entry.get("summary_detail")
    if isinstance(sd, dict):
        u = _img_src_from_html(sd.get("value") or "")
        if u:
            return u
    for block in entry.get("content") or []:
        if isinstance(block, dict):
            u = _img_src_from_html(block.get("value") or "")
            if u:
                return u
    return ""


def _extract_image_url(entry) -> str:
    for item in entry.get("media_content") or []:
        u = _url_from_media_dict(item)
        if not u:
            continue
        typ = (item.get("type") or "").lower()
        medium = (item.get("medium") or "").lower()
        if typ.startswith("image/") or medium == "image" or _looks_like_image_url(u):
            return u
    for item in entry.get("media_content") or []:
        u = _url_from_media_dict(item)
        if u and _looks_like_image_url(u):
            return u

    for item in entry.get("media_thumbnail") or []:
        u = _url_from_media_dict(item)
        if u:
            return u

    img = entry.get("image")
    if isinstance(img, dict):
        u = (img.get("href") or img.get("url") or "").strip()
        if u.startswith("http://") or u.startswith("https://"):
            return u
    elif isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
        return img.strip()

    for enc in entry.get("enclosures") or []:
        if not isinstance(enc, dict):
            continue
        u = (enc.get("href") or enc.get("url") or "").strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        typ = (enc.get("type") or "").lower()
        if typ.startswith("image/") or (not typ and _looks_like_image_url(u)):
            return u

    for link in entry.get("links") or []:
        if not isinstance(link, dict):
            continue
        typ = (link.get("type") or "").lower()
        if not typ.startswith("image/"):
            continue
        u = (link.get("href") or link.get("url") or "").strip()
        if u.startswith("http://") or u.startswith("https://"):
            return u

    return _image_from_entry_html(entry)


def _normalize_page_image_url(base: str, raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return urljoin(base, u)


def _extract_image_from_article_page(
    article_url: str, timeout: float = IMAGE_PAGE_TIMEOUT
) -> str:
    if not article_url or not (
        article_url.startswith("http://") or article_url.startswith("https://")
    ):
        return ""
    try:
        resp = requests.get(
            article_url, timeout=timeout, headers=HTTP_HEADERS
        )
        resp.raise_for_status()
    except Exception:
        return ""

    try:
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return ""

    tag = soup.find("meta", property="og:image")
    if tag and tag.get("content"):
        u = _normalize_page_image_url(article_url, tag["content"])
        if u:
            return u

    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if not tag:
        tag = soup.find("meta", property="twitter:image")
    if tag and tag.get("content"):
        u = _normalize_page_image_url(article_url, tag["content"])
        if u:
            return u

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
                return u

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
            return u

    return ""


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


def _category_keyword_match(text: str, words: List[str]) -> bool:
    """
    True if any keyword appears in the lowercased text (title + summary snippet).
    Short tokens (e.g. 'ot', 'nhl') use whole-word match so we don't match 'not' or 'another'.
    Multi-word phrases use substring match.
    """
    for w in words:
        w = w.lower()
        if " " in w:
            if w in text:
                return True
            continue
        if w == "ot":
            if re.search(r"\b(?:ot|o\.t\.)\b", text):
                return True
            continue
        if len(w) <= 4 and w.isalpha():
            if re.search(rf"\b{re.escape(w)}\b", text):
                return True
        else:
            if w in text:
                return True
    return False


def infer_category(title: str, summary: str = "") -> str:
    """Rules-based topic; uses title and optional RSS/summary text to reduce 'Other'."""
    text = f"{title} {summary}"[:2000].lower()

    politics_kw = [
        "election",
        "government",
        "policy",
        "parliament",
        "ford",
        "minister",
        "polling",
    ]
    crime_kw = ["police", "killed", "charged", "murder", "assault", "rcmp", "suspect"]
    sports_kw = [
        "nhl",
        "leafs",
        "hockey",
        "overtime",
        "ot",
        "curling",
        "team",
        "wins",
        "game",
        "tournament",
        "league",
        "olympic",
        "olympics",
        "soccer",
        "nba",
        "nfl",
        "mlb",
        "golf",
        "tennis",
        "playoffs",
        "championship",
        "world series",
        "stanley cup",
        "super bowl",
    ]
    business_kw = ["budget", "economy", "prices", "tax", "funding"]
    health_kw = ["health", "hospital", "care", "treatment"]
    canada_kw = ["canada", "canadian", "federal"]
    world_kw = [
        "u.s.",
        "trump",
        "iran",
        "iraq",
        "nato",
        "china",
        "europe",
        "russia",
        "ukraine",
        "paris",
        "france",
        "south korea",
        "international",
        "world",
        "korea",
    ]
    tech_kw = [
        "tech",
        "technology",
        "software",
        "cyber",
        "ai",
        "artificial intelligence",
        "apple",
        "google",
        "microsoft",
    ]
    entertainment_kw = [
        "entertainment",
        "celebrity",
        "oscar",
        "grammy",
        "concert",
        "album",
        "netflix",
        "hollywood",
        "film",
        "movie",
    ]

    if _category_keyword_match(text, politics_kw):
        return "Politics"
    if _category_keyword_match(text, crime_kw):
        return "Crime"
    if _category_keyword_match(text, sports_kw):
        return "Sports"
    if _category_keyword_match(text, business_kw):
        return "Business"
    if _category_keyword_match(text, health_kw):
        return "Health"
    if _category_keyword_match(text, canada_kw):
        return "Canada"
    if _category_keyword_match(text, world_kw):
        return "World"
    if _category_keyword_match(text, tech_kw):
        return "Technology"
    if _category_keyword_match(text, entertainment_kw):
        return "Entertainment"
    return "Other"


def infer_region(title: str, summary: str = "") -> str:
    """Rules-based region; scans title + optional summary for provinces and places."""
    text = f"{title} {summary}"[:2000].lower()

    def matches(words):
        return any(w in text for w in words)

    if matches(["ottawa"]):
        return "Ottawa"
    if matches(["ontario", "toronto", "ford"]):
        return "Ontario"
    if matches(["alberta", "calgary", "edmonton"]):
        return "Alberta"
    if matches(["quebec", "montreal"]):
        return "Quebec"
    if matches(["vancouver", "b.c.", "british columbia"]):
        return "British Columbia"
    if matches(["winnipeg", "manitoba"]):
        return "Manitoba"
    if matches(["saskatoon", "regina", "saskatchewan"]):
        return "Saskatchewan"
    if matches(["halifax", "nova scotia"]):
        return "Nova Scotia"
    if matches(["fredericton", "moncton", "new brunswick"]):
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
    if matches(["canada", "canadian", "federal"]):
        return "Canada"
    if matches(["u.s.", "trump", "iran", "iraq", "nato", "china", "europe"]):
        return "World"
    return "Other"


def normalize_link(link: str) -> str:
    cleaned = (link or "").strip().lower()
    while cleaned.endswith("/") and len(cleaned) > 1:
        cleaned = cleaned[:-1]
    return cleaned


def normalize_title_for_dedup(title: str) -> str:
    t = (title or "").strip().lower()
    t = t.replace("–", " ").replace("—", " ").replace("-", " ")
    t = re.sub(r"[^\w\s]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


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
    source_name: str, _feed_url: str, content: bytes
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
            # Cheap placeholder; real summary runs after dedupe + top-N cut (see fetch_all_feeds).
            summary = normalize_stored_summary(
                (headline or "News update.").strip() or "News update.",
                title,
                article_text or None,
            )
            category = infer_category(headline, article_text)
            region = infer_region(headline, article_text)
            # RSS-only images here — article-page scrape is limited to top stories later.
            image_url = _extract_image_url(entry) or ""

            feed_label = specific_source_label(source_name)
            label = refine_article_source(link, feed_label)
            source_group = infer_source_group(label)
            if label.lower().startswith("cbc"):
                source_group = "CBC"

            _maybe_log_cbc_source_debug(feed_label, label, source_group, link)

            article = {
                "title": title or link,
                "summary": summary,
                "source": label,
                "source_group": source_group,
                "link": link,
                "published": published_str,
                "category": category,
                "region": region,
                "image_url": image_url,
                "published_raw": published_dt,
                # Kept for DB rss_excerpt + lazy AI later; trimmed at save.
                "rss_excerpt": (article_text or "")[:12000],
            }
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
      title, summary, source, link, published, category, region, image_url
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

    return _parse_feed_response(source_name, url, resp.content)


def fetch_all_feeds() -> List[Dict]:
    """
    Fetch articles from all configured RSS feeds, then:
      - combine them into a single list,
      - deduplicate by normalized link, then exact same normalized title,
      - sort by published date (latest first),
      - keep up to MAX_INGEST_ARTICLES for clustering + storage,
      - image-page fetch only for the top IMAGE_SCRAPE_MAX_ARTICLES without RSS images.

    OpenAI summaries are not run here — only on page view (see main.py + page_summaries).
    """
    global _CBC_SOURCE_DEBUG_LOGGED
    _CBC_SOURCE_DEBUG_LOGGED = False

    t_total_start = time.time()
    all_items: List[Dict] = []

    t_feed_start = time.time()
    for source_name, feed_url in FEEDS:
        print(f"[fetch_news] Fetching {source_name} ({feed_url})")
        t_req_start = time.time()
        try:
            response = requests.get(
                feed_url, timeout=REQUEST_TIMEOUT, headers=HTTP_HEADERS
            )
            elapsed = time.time() - t_req_start
            print(
                f"[fetch_news] {source_name}: status={response.status_code}, "
                f"time={elapsed:.3f}s"
            )
            response.raise_for_status()
        except Exception as e:
            print(f"[fetch_news] {source_name}: skipped due to error: {e}")
            continue

        try:
            items = _parse_feed_response(source_name, feed_url, response.content)
            all_items.extend(items)
        except Exception as e:
            print(f"[fetch_news] {source_name}: skipped due to error: {e}")
            continue

    # If everything failed, try BBC over HTTPS once (common HTTP/redirect issues)
    if not all_items:
        print(
            "[fetch_news] WARNING: no articles yet; emergency BBC HTTPS fallback"
        )
        try:
            r = requests.get(
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                timeout=REQUEST_TIMEOUT,
                headers=HTTP_HEADERS,
            )
            r.raise_for_status()
            all_items.extend(
                _parse_feed_response(
                    "BBC",
                    "https://feeds.bbci.co.uk/news/world/rss.xml",
                    r.content,
                )
            )
        except Exception as e:
            print(f"[fetch_news] BBC World (emergency): skipped due to error: {e}")

    feed_fetch_s = time.time() - t_feed_start
    print(
        f"[fetch_news] SUCCESSFUL SOURCES:",
        list(set(a["source"] for a in all_items if a.get("source"))),
    )

    combined_count_before_dedupe = len(all_items)
    sources_before_dedupe = sorted(
        {a.get("source", "") for a in all_items if a.get("source")}
    )
    print(f"[fetch_news] combined_count_before_dedupe={combined_count_before_dedupe}")
    print(f"[fetch_news] sources_before_dedupe={sources_before_dedupe}")

    t_dedupe_start = time.time()
    # Conservative dedupe: same normalized link OR exact same normalized title (no fuzzy match)
    seen_links = set()
    seen_titles = set()
    deduped: List[Dict] = []

    for item in all_items:
        norm_link = normalize_link(item.get("link", ""))
        norm_title = normalize_title_for_dedup(item.get("title", ""))

        if norm_link and norm_link in seen_links:
            continue
        if norm_title and norm_title in seen_titles:
            continue

        deduped.append(item)
        if norm_link:
            seen_links.add(norm_link)
        if norm_title:
            seen_titles.add(norm_title)

    x = combined_count_before_dedupe
    y = len(deduped)
    print(f"[fetch_news] deduplicated from {x} to {y} articles")
    sources_after_dedupe = sorted(
        {a.get("source", "") for a in deduped if a.get("source")}
    )
    print(f"[fetch_news] sources_after_dedupe={sources_after_dedupe}")

    deduped.sort(
        key=lambda item: item.get("published_raw", datetime.utcnow()),
        reverse=True,
    )

    limited = deduped[:MAX_INGEST_ARTICLES]
    dedupe_s = time.time() - t_dedupe_start

    t_image_start = time.time()
    for idx, article in enumerate(limited):
        if idx < IMAGE_SCRAPE_MAX_ARTICLES:
            if not (article.get("image_url") or "").strip():
                try:
                    article["image_url"] = (
                        _extract_image_from_article_page(
                            article.get("link") or ""
                        )
                        or ""
                    )
                except Exception:
                    article["image_url"] = ""
        else:
            if not (article.get("image_url") or "").strip():
                article["image_url"] = ""
    image_s = time.time() - t_image_start

    trimmed: List[Dict] = []
    for item in limited:
        trimmed.append(dict(item))

    total_s = time.time() - t_total_start
    print(
        f"[fetch_news] timing: feed_fetch={feed_fetch_s:.3f}s "
        f"dedupe_sort_cap={dedupe_s:.3f}s "
        f"image_scrape={image_s:.3f}s total_fetch_all_feeds={total_s:.3f}s "
        f"(clustering + lazy summaries in API /news)"
    )

    return trimmed
