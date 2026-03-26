"""
Deterministic, rule-based topic classification for articles.

Separate from story clustering: `cluster_id` groups the same story across outlets;
`topic_category` is a high-level editorial topic label only.

No LLM. Order of application:
  1) feed_registry_key hints (when unambiguous)
  2) source / feed display name hints
  3) URL path segments (publisher-specific patterns)
  4) keyword buckets on normalized title + rss_excerpt (fixed priority)
  5) weak registry fallbacks, then Other
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Canonical labels (Title Case) — keep stable for API / UI chips.
TOPIC_CATEGORIES: Tuple[str, ...] = (
    "Business",
    "Entertainment",
    "Sports",
    "Politics",
    "Crime",
    "Health",
    "Technology",
    "Canada",
    "Other",
)


def _keyword_match(text: str, words: List[str]) -> bool:
    """
    True if any keyword matches in lowercased text (same spirit as fetch_news).
    Short alphabetic tokens use word boundaries; phrases use substring match.
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


def _norm_blob(title: str, excerpt: str) -> str:
    return f"{title} {excerpt}"[:12000].lower()


def _topic_from_registry_key(key: str) -> Optional[str]:
    """Strong, unambiguous registry_key → topic (substring rules)."""
    k = (key or "").strip().lower()
    if not k:
        return None
    if "politic" in k:
        return "Politics"
    if "sport" in k or k.endswith("_nhl") or "olympic" in k:
        return "Sports"
    if "business" in k or "financial" in k or "fp_" in k or "markets" in k:
        return "Business"
    if "entertainment" in k or "arts" in k or "movie" in k:
        return "Entertainment"
    if "health" in k or "wellness" in k:
        return "Health"
    if "tech" in k or "science" in k or "innovation" in k:
        return "Technology"
    if "crime" in k or "justice" in k:
        return "Crime"
    return None


def _topic_from_source_name(source: str) -> Optional[str]:
    """Desk / section baked into the feed display name (e.g. 'Global News - Politics')."""
    s = (source or "").strip().lower()
    if not s:
        return None
    # Order: specific desks first
    if "politic" in s:
        return "Politics"
    if "sport" in s:
        return "Sports"
    if "business" in s or "financial" in s or "money" in s:
        return "Business"
    if "entertainment" in s or "arts" in s:
        return "Entertainment"
    if "health" in s:
        return "Health"
    if "tech" in s or "science" in s:
        return "Technology"
    if "crime" in s or "justice" in s:
        return "Crime"
    return None


def _topic_from_url(link: str) -> Optional[str]:
    """Path-based hints (English Canadian publishers)."""
    if not link:
        return None
    try:
        p = urlparse(link)
        path = (p.path or "").lower()
        joined = f"{p.netloc or ''}/{path}"
    except Exception:
        return None

    # --- CBC ---
    if "cbc.ca" in joined:
        if "/news/politics" in path or "/politics/" in path:
            return "Politics"
        if "/news/sports" in path or "/sports/" in path:
            return "Sports"
        if "/news/business" in path or "/business/" in path:
            return "Business"
        if "/news/health" in path or "/health/" in path:
            return "Health"
        if "/news/technology" in path or "/news/science" in path or "/technology/" in path:
            return "Technology"
        if "/news/entertainment" in path or "/entertainment/" in path:
            return "Entertainment"
        if "/news/canada" in path or "/canada/" in path:
            return "Canada"
        if "/news/world" in path:
            return "Other"

    # --- Global News ---
    if "globalnews.ca" in joined:
        if "/politics" in path:
            return "Politics"
        if "/entertainment" in path:
            return "Entertainment"
        if "/sports" in path:
            return "Sports"
        if "/health" in path:
            return "Health"
        if "/business" in path or "/money" in path or "/economy" in path:
            return "Business"
        if "/crime" in path or "/justice" in path:
            return "Crime"
        if "/canada" in path or "/national" in path:
            return "Canada"
        if "/tech" in path or "/science" in path:
            return "Technology"

    # --- CTV / generic ---
    if "ctvnews.ca" in joined or "thestar.com" in joined or "nationalpost.com" in joined:
        if "/politics" in path or "/federal-politics" in path or "/provincial-politics" in path:
            return "Politics"
        if "/sports" in path:
            return "Sports"
        if "/entertainment" in path:
            return "Entertainment"
        if "/business" in path:
            return "Business"
        if "/health" in path:
            return "Health"
        if "/crime" in path or "/justice" in path:
            return "Crime"
        if "/tech" in path:
            return "Technology"

    # --- Toronto Sun / Sun chain ---
    if "torontosun.com" in joined or ".sun." in joined:
        if "/news/national" in path or "/news/provincial" in path:
            return "Canada"
        if "/sports" in path:
            return "Sports"
        if "/entertainment" in path:
            return "Entertainment"

    return None


def _topic_from_keywords(text: str) -> str:
    """
    Single topic from keyword buckets. Fixed priority (first match wins):
    Politics → Crime → Sports → Health → Technology → Business → Entertainment → Canada → Other
    """
    politics_kw = [
        "election",
        "government",
        "parliament",
        "minister",
        "prime minister",
        "premier",
        "senate",
        "mp ",
        " mps",
        "liberal party",
        "conservative party",
        "ndp",
        "trudeau",
        "ford government",
        "policy",
        "polling",
        "white house",
        "g7",
        "g20",
        "nato summit",
        "united nations",
    ]
    crime_kw = [
        "police",
        "rcmp",
        "charged",
        "murder",
        "homicide",
        "assault",
        "shooting",
        "stabbing",
        "suspect",
        "arrest",
        "court",
        "sentenced",
        "trial",
        "investigation",
        "warrant",
    ]
    sports_kw = [
        "nhl",
        "nba",
        "nfl",
        "mlb",
        "leafs",
        "canucks",
        "hockey",
        "curling",
        "soccer",
        "olympic",
        "olympics",
        "stanley cup",
        "super bowl",
        "playoffs",
        "championship",
        "tournament",
        "raptors",
        "blue jays",
        "overtime",
        "ot",
        "world series",
        "golf",
        "tennis",
        "cfl",
    ]
    health_kw = [
        "health",
        "hospital",
        "patient",
        "doctor",
        "nurse",
        "covid",
        "vaccine",
        "mental health",
        "cancer",
        "treatment",
        "outbreak",
        "disease",
        "pharmacare",
    ]
    tech_kw = [
        "technology",
        "tech",
        "software",
        "cyber",
        "artificial intelligence",
        "apple",
        "google",
        "microsoft",
        "meta",
        "tesla",
        "startup",
        "cryptocurrency",
        "bitcoin",
        "data breach",
        "hack",
        "hacking",
        "semiconductor",
        "chip",
        "5g",
        "smartphone",
    ]
    business_kw = [
        "economy",
        "economic",
        "stock",
        "stocks",
        "market",
        "markets",
        "bank of canada",
        "interest rate",
        "inflation",
        "recession",
        "budget",
        "tax",
        "tariff",
        "trade deal",
        "ceo",
        "earnings",
        "housing market",
        "mortgage",
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
        "television",
        "tv series",
        "actor",
        "actress",
        "director",
    ]
    canada_kw = [
        "canada",
        "canadian",
        "federal",
        "from coast to coast",
        "ottawa",
        "parliament hill",
        "house of commons",
    ]

    if _keyword_match(text, politics_kw):
        return "Politics"
    if _keyword_match(text, crime_kw):
        return "Crime"
    if _keyword_match(text, sports_kw):
        return "Sports"
    if _keyword_match(text, health_kw):
        return "Health"
    if _keyword_match(text, tech_kw):
        return "Technology"
    if _keyword_match(text, business_kw):
        return "Business"
    if _keyword_match(text, entertainment_kw):
        return "Entertainment"
    if _keyword_match(text, canada_kw):
        return "Canada"
    return "Other"


def _weak_registry_canada(feed_key: str) -> bool:
    k = (feed_key or "").strip().lower()
    return k in ("national_global_canada",) or "global_canada" in k


def assign_topic_category(article: Dict[str, Any]) -> str:
    """
    Assign exactly one TOPIC_CATEGORIES label.
    Does not read or write cluster_id.
    """
    title = str(article.get("title") or "")
    excerpt = str(article.get("rss_excerpt") or "")
    link = str(article.get("link") or "")
    feed_key = str(article.get("feed_registry_key") or "")
    source = str(article.get("source") or "")

    t = _topic_from_registry_key(feed_key)
    if t:
        return t

    t = _topic_from_source_name(source)
    if t:
        return t

    t = _topic_from_url(link)
    if t:
        return t

    blob = _norm_blob(title, excerpt)
    k = _topic_from_keywords(blob)
    if k != "Other":
        return k

    if _weak_registry_canada(feed_key):
        return "Canada"

    return "Other"


def log_topic_classification_batch(
    articles: List[Dict[str, Any]],
    *,
    log_prefix: str,
    stage: str = "post_cluster",
) -> None:
    """Log counts, sample titles per category, and Other total."""
    from collections import Counter, defaultdict

    counts: Counter[str] = Counter()
    samples: Dict[str, List[str]] = defaultdict(list)

    for a in articles:
        cat = (a.get("topic_category") or a.get("category") or "Other").strip() or "Other"
        counts[cat] += 1
        if len(samples[cat]) < 4:
            samples[cat].append((a.get("title") or "")[:140])

    order = [c for c in TOPIC_CATEGORIES if c in counts] + sorted(
        x for x in counts if x not in TOPIC_CATEGORIES
    )
    print(
        f"[topic_class] [{log_prefix}] stage={stage} "
        f"counts={{{', '.join(f'{k}:{counts[k]}' for k in order)}}} "
        f"other_n={counts.get('Other', 0)} total={len(articles)}"
    )
    for cat in order:
        titles = samples.get(cat) or []
        if titles:
            print(f"[topic_class] [{log_prefix}] sample_titles[{cat}]={titles!r}")
