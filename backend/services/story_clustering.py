"""
story_clustering.py

Hybrid clustering: link dedupe → lexical similarity (titles + excerpts) → optional
embedding merge for borderline pairs. Preserves output shape for ranking/DB.

Embeddings are optional (OPENAI_API_KEY); lexical stages run without any API.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse, urlunparse

import numpy as np
import requests
from env import get_openai_api_key


def _l2_normalize_rows(X: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (X / norms).astype(np.float32)

# --- OpenAI embeddings (optional, Stage C only) ----------------------------
_DEFAULT_EMBED_MODEL = "text-embedding-3-small"
# Cosine similarity threshold for borderline pairs (higher = stricter merge).
_DEFAULT_EMBED_BORDER_COS = 0.88

# --- Lexical thresholds (tune via env) --------------------------------------
_DEFAULT_JACCARD_STRONG = 0.52
_DEFAULT_RATIO_STRONG = 0.86
_DEFAULT_CONTAIN_MIN_SHORT = 18
_DEFAULT_CONTAIN_LEN_RATIO = 0.48

# Borderline band for Stage C (must be inside this band to ask embeddings).
_DEFAULT_JACCARD_LO = 0.28
_DEFAULT_JACCARD_HI = 0.58
_DEFAULT_RATIO_LO = 0.52
_DEFAULT_RATIO_HI = 0.82

# When categories disagree (both set), require stricter lexical match.
_DEFAULT_CROSS_CAT_RATIO = 0.93
_DEFAULT_CROSS_CAT_JACCARD = 0.62

# Sports matchup headlines: stricter merge unless nearly identical.
_DEFAULT_SPORTS_RATIO = 0.87
_DEFAULT_SPORTS_JACCARD = 0.55

# Generic news prefixes / boilerplate (stripped deterministically).
_BORING_PREFIX = re.compile(
    r"^(breaking|just in|watch live|live updates?|live:|watch:|exclusive|update:?)\s*[:|\-–]?\s*",
    re.I,
)
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WS = re.compile(r"\s+")

# Minimal English stopwords for Jaccard (deterministic, small).
_STOP: Set[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "as",
        "by",
        "with",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "not",
        "no",
        "yes",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "than",
        "then",
        "so",
        "if",
        "about",
        "into",
        "over",
        "after",
        "before",
        "out",
        "up",
        "down",
        "more",
        "most",
        "some",
        "such",
        "just",
        "also",
        "only",
        "even",
        "both",
        "all",
        "any",
        "each",
        "other",
        "new",
        "say",
        "says",
        "said",
        "here",
        "how",
        "what",
        "when",
        "where",
        "why",
        "who",
        "which",
    }
)


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._p = list(range(n))
        self._r = [0] * n

    def find(self, x: int) -> int:
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self._r[ra] < self._r[rb]:
            ra, rb = rb, ra
        self._p[rb] = ra
        if self._r[ra] == self._r[rb]:
            self._r[ra] += 1
        return True


def _normalize_link(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        scheme = (p.scheme or "https").lower()
        netloc = (p.netloc or "").lower()
        if not netloc:
            return u.lower().strip()
        path = (p.path or "").rstrip("/") or "/"
        return urlunparse((scheme, netloc, path, "", "", "")).lower()
    except Exception:
        return u.lower().strip()


def _strip_boring_prefix(text: str) -> str:
    t = (text or "").strip()
    prev = None
    while prev != t:
        prev = t
        t = _BORING_PREFIX.sub("", t).strip()
    return t


def _normalize_words(text: str) -> str:
    t = (text or "").strip().lower()
    t = _strip_boring_prefix(t)
    t = _NON_WORD.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return t


def normalized_title(article: Dict) -> str:
    """Normalized title only (for lexical match)."""
    return _normalize_words((article.get("title") or "").strip() or "untitled")


def normalized_cluster_text(article: Dict) -> str:
    """
    Deterministic text for clustering: normalized title + cleaned rss_excerpt.
    Does not use AI summary.
    """
    title = _normalize_words((article.get("title") or "").strip() or "untitled")
    ex = (article.get("rss_excerpt") or "").strip()
    if not ex:
        return title
    ex_n = _normalize_words(ex[:4000])
    if not ex_n:
        return title
    return f"{title} {ex_n}".strip()


def _tokens(s: str) -> Set[str]:
    return {w for w in s.split() if len(w) > 1 and w not in _STOP}


def _jaccard(a: str, b: str) -> float:
    sa, sb = _tokens(a), _tokens(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _containment_ok(short: str, long: str, min_short: int, min_ratio: float) -> bool:
    if len(short) < min_short or len(long) < min_short:
        return False
    if len(short) > len(long):
        short, long = long, short
    if len(short) / max(len(long), 1) < min_ratio:
        return False
    return short in long


def _looks_sports_matchup(title: str) -> bool:
    t = (title or "").lower()
    if " vs " in t or " vs. " in t or " @ " in t:
        return True
    return bool(re.search(r"\b\d{1,3}\s*[-–]\s*\d{1,3}\b", t))


def _story_topic_label(a: Dict) -> str:
    """Lexical-merge guard label (topic vs topic). Uses topic_category when set."""
    return (a.get("topic_category") or a.get("category") or "").strip().lower()


def _category_conflict(a: Dict, b: Dict) -> bool:
    ca = _story_topic_label(a)
    cb = _story_topic_label(b)
    return bool(ca and cb and ca != cb)


def _lexical_merge_allowed(
    a: Dict,
    b: Dict,
    title_a: str,
    title_b: str,
    full_a: str,
    full_b: str,
    *,
    j_strong: float,
    r_strong: float,
    contain_min: int,
    contain_ratio: float,
    cross_cat_r: float,
    cross_cat_j: float,
    sports_r: float,
    sports_j: float,
) -> bool:
    if title_a == title_b and len(title_a) >= 12:
        return True

    ja = _jaccard(full_a, full_b)
    ra = _ratio(title_a, title_b)

    cross = _category_conflict(a, b)
    sports_both = _looks_sports_matchup(a.get("title") or "") and _looks_sports_matchup(
        b.get("title") or ""
    )

    if cross:
        if ja >= cross_cat_j and ra >= cross_cat_r:
            return True
        return False

    if sports_both:
        if ja >= sports_j and ra >= sports_r:
            return True
        if title_a == title_b:
            return True
        return False

    if ja >= j_strong and ra >= r_strong:
        return True

    if ra >= 0.92 and ja >= 0.38:
        return True

    shorter, longer = (
        (title_a, title_b) if len(title_a) <= len(title_b) else (title_b, title_a)
    )
    if _containment_ok(shorter, longer, contain_min, contain_ratio):
        return True

    return False


def _embedding_candidate_pair(
    title_a: str,
    title_b: str,
    full_a: str,
    full_b: str,
    *,
    j_lo: float,
    j_hi: float,
    r_lo: float,
    r_hi: float,
    j_strong: float,
    r_strong: float,
) -> bool:
    """
    True if the pair is not obviously unrelated and not already a clear lexical duplicate.
    Used to limit expensive embedding comparisons.
    """
    ja = _jaccard(full_a, full_b)
    ra = _ratio(title_a, title_b)
    # No signal
    weak_floor_j = max(0.18, j_lo * 0.72)
    weak_floor_r = max(0.42, r_lo * 0.88)
    if ja < weak_floor_j and ra < weak_floor_r:
        return False
    # Strong duplicate — Stage B should already have merged; avoid redundant embed work
    if ja >= min(0.72, j_hi + 0.12) and ra >= r_strong - 0.03:
        return False
    if ra >= 0.91 and ja >= 0.42:
        return False
    # Borderline band (overlap without certainty)
    in_j_band = j_lo <= ja <= j_hi + 0.08
    in_r_band = r_lo <= ra <= r_hi + 0.06
    mid_overlap = (0.3 <= ja <= 0.66) and (r_lo - 0.05 <= ra < r_strong - 0.03)
    return in_j_band or in_r_band or mid_overlap


def _fetch_openai_embeddings(texts: List[str]) -> np.ndarray:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    model = (os.environ.get("OPENAI_EMBEDDING_MODEL") or _DEFAULT_EMBED_MODEL).strip()
    resp = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    rows = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
    vectors = [np.array(r["embedding"], dtype=np.float32) for r in rows]
    if len(vectors) != len(texts):
        raise RuntimeError("embedding count mismatch")
    return np.vstack(vectors)


def _merge_coverage_from_cluster(members: List[Dict]) -> Dict[str, str]:
    rank_map = {"city": 0, "civic": 0, "province": 1, "national": 2}
    tagged = [a for a in members if (a.get("coverage_level") or "").strip()]
    if not tagged:
        return {
            "coverage_city": "",
            "coverage_province": "",
            "coverage_level": "",
            "feed_registry_key": "",
        }

    def cov_rank(a: Dict) -> int:
        cl = (a.get("coverage_level") or "").strip().lower()
        return rank_map.get(cl, 99)

    best = min(tagged, key=cov_rank)
    return {
        "coverage_city": (best.get("coverage_city") or "").strip(),
        "coverage_province": (best.get("coverage_province") or "").strip(),
        "coverage_level": (best.get("coverage_level") or "").strip(),
        "feed_registry_key": (best.get("feed_registry_key") or "").strip(),
    }


def _components(uf: _UnionFind, n: int) -> Dict[int, List[int]]:
    buckets: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        buckets[uf.find(i)].append(i)
    return dict(buckets)


def _log_cluster_quality(
    by_root: Dict[int, List[int]],
    articles: List[Dict],
    *,
    stage_c_merges: int,
    used_embeddings: bool,
) -> None:
    n_art = len(articles)
    sizes = sorted((len(m) for m in by_root.values()), reverse=True)
    n_cl = len(by_root)
    singletons = sum(1 for m in by_root.values() if len(m) == 1)
    multi = n_cl - singletons
    pct = (100.0 * singletons / n_cl) if n_cl else 0.0
    largest = sizes[:8]

    print(
        "[cluster] quality "
        f"total_articles={n_art} total_clusters={n_cl} "
        f"singleton_clusters={singletons} singleton_pct={pct:.1f}% "
        f"multi_article_clusters={multi} "
        f"largest_cluster_sizes={largest} "
        f"stage_c_pair_merges={stage_c_merges} "
        f"embeddings_used={used_embeddings}"
    )

    shown = 0
    for root in sorted(by_root.keys(), key=lambda r: -len(by_root[r])):
        mem = by_root[root]
        if len(mem) < 2:
            continue
        titles = [(articles[i].get("title") or "")[:120] for i in mem[:6]]
        print(
            f"[cluster] sample_multi id={root} size={len(mem)} "
            f"titles={titles!r}"
        )
        shown += 1
        if shown >= 5:
            break


def cluster_articles(articles: List[Dict]) -> List[Dict]:
    """
    Cluster articles, then collapse each cluster to *one* main row.

    Pipeline:
      A) Same normalized link -> same cluster.
      B) Lexical similarity on normalized titles + cluster text (Jaccard, ratio,
         containment) with category/sports guards.
      C) Optional: OpenAI embeddings for borderline pairs only.

    Output keys unchanged: cluster_id, sources, related_links, trending_score, etc.
    """
    if not articles:
        return []

    n = len(articles)
    titles_t = [normalized_title(a) for a in articles]
    full_t = [normalized_cluster_text(a) for a in articles]
    links = [_normalize_link((a.get("link") or "").strip()) for a in articles]

    j_strong = float(os.environ.get("CLUSTER_LEX_JACCARD_STRONG", str(_DEFAULT_JACCARD_STRONG)))
    r_strong = float(os.environ.get("CLUSTER_LEX_RATIO_STRONG", str(_DEFAULT_RATIO_STRONG)))
    contain_min = int(os.environ.get("CLUSTER_LEX_CONTAIN_MIN", str(_DEFAULT_CONTAIN_MIN_SHORT)))
    contain_ratio = float(
        os.environ.get("CLUSTER_LEX_CONTAIN_LEN_RATIO", str(_DEFAULT_CONTAIN_LEN_RATIO))
    )
    cross_r = float(os.environ.get("CLUSTER_CROSS_CAT_RATIO", str(_DEFAULT_CROSS_CAT_RATIO)))
    cross_j = float(os.environ.get("CLUSTER_CROSS_CAT_JACCARD", str(_DEFAULT_CROSS_CAT_JACCARD)))
    sports_r = float(os.environ.get("CLUSTER_SPORTS_RATIO", str(_DEFAULT_SPORTS_RATIO)))
    sports_j = float(os.environ.get("CLUSTER_SPORTS_JACCARD", str(_DEFAULT_SPORTS_JACCARD)))

    j_lo = float(os.environ.get("CLUSTER_BORDER_JACCARD_LO", str(_DEFAULT_JACCARD_LO)))
    j_hi = float(os.environ.get("CLUSTER_BORDER_JACCARD_HI", str(_DEFAULT_JACCARD_HI)))
    r_lo = float(os.environ.get("CLUSTER_BORDER_RATIO_LO", str(_DEFAULT_RATIO_LO)))
    r_hi = float(os.environ.get("CLUSTER_BORDER_RATIO_HI", str(_DEFAULT_RATIO_HI)))
    embed_cos = float(
        os.environ.get("CLUSTER_EMBED_BORDER_COS", str(_DEFAULT_EMBED_BORDER_COS))
    )

    uf = _UnionFind(n)
    stage_a = 0
    first_by_link: Dict[str, int] = {}
    for i, lk in enumerate(links):
        if not lk:
            continue
        if lk in first_by_link:
            if uf.union(i, first_by_link[lk]):
                stage_a += 1
        else:
            first_by_link[lk] = i

    stage_b = 0
    for i in range(n):
        for j in range(i + 1, n):
            if _lexical_merge_allowed(
                articles[i],
                articles[j],
                titles_t[i],
                titles_t[j],
                full_t[i],
                full_t[j],
                j_strong=j_strong,
                r_strong=r_strong,
                contain_min=contain_min,
                contain_ratio=contain_ratio,
                cross_cat_r=cross_r,
                cross_cat_j=cross_j,
                sports_r=sports_r,
                sports_j=sports_j,
            ):
                if uf.union(i, j):
                    stage_b += 1

    stage_c = 0
    used_embeddings = False
    E: Optional[np.ndarray] = None
    if get_openai_api_key() and n >= 2:
        try:
            E = _fetch_openai_embeddings(full_t)
            E = _l2_normalize_rows(E)
            used_embeddings = True
        except Exception as e:
            print(f"[cluster] stage_c embeddings unavailable ({e}); skipping")

    if E is not None:
        for i in range(n):
            for j in range(i + 1, n):
                if uf.find(i) == uf.find(j):
                    continue
                if _category_conflict(articles[i], articles[j]):
                    continue
                if not _embedding_candidate_pair(
                    titles_t[i],
                    titles_t[j],
                    full_t[i],
                    full_t[j],
                    j_lo=j_lo,
                    j_hi=j_hi,
                    r_lo=r_lo,
                    r_hi=r_hi,
                    j_strong=j_strong,
                    r_strong=r_strong,
                ):
                    continue
                sim = float(np.dot(E[i], E[j]))
                if sim >= embed_cos:
                    if uf.union(i, j):
                        stage_c += 1

    by_root = _components(uf, n)
    roots_sorted = sorted(by_root.keys())
    root_to_cid = {r: k for k, r in enumerate(roots_sorted)}

    print(
        f"[cluster] pipeline stages link_dedupe_unions={stage_a} "
        f"lexical_unions={stage_b} embed_border_unions={stage_c}"
    )
    _log_cluster_quality(
        by_root,
        articles,
        stage_c_merges=stage_c,
        used_embeddings=used_embeddings,
    )

    out: List[Dict] = []
    for root in roots_sorted:
        idxs = by_root[root]
        cl = [articles[i] for i in idxs]
        cid = root_to_cid[root]
        trending_score = len(cl)

        main = max(cl, key=lambda a: a.get("published_raw") or datetime.min)

        sources: List[str] = []
        seen_src = set()
        for a in cl:
            src = (a.get("source") or "").strip()
            if src and src not in seen_src:
                seen_src.add(src)
                sources.append(src)

        main_link = (main.get("link") or "").strip()
        related_links: List[str] = []
        seen_links = set()
        for a in cl:
            lk = (a.get("link") or "").strip()
            if lk and lk != main_link and lk not in seen_links:
                seen_links.add(lk)
                related_links.append(lk)

        excerpt = (main.get("rss_excerpt") or main.get("_rss_article_text") or "")[
            :12000
        ]
        cov = _merge_coverage_from_cluster(cl)
        out.append(
            {
                "title": main.get("title"),
                "summary": main.get("summary"),
                "summary_status": main.get("summary_status") or "pending",
                "source": main.get("source"),
                "source_group": main.get("source_group"),
                "sources": sources,
                "link": main_link,
                "related_links": related_links,
                "published": main.get("published"),
                "category": main.get("category"),
                "topic_category": main.get("topic_category"),
                "region": main.get("region"),
                "coverage_city": cov["coverage_city"],
                "coverage_province": cov["coverage_province"],
                "coverage_level": cov["coverage_level"],
                "feed_registry_key": cov["feed_registry_key"],
                "image_url": main.get("image_url"),
                "cluster_id": cid,
                "trending_score": trending_score,
                "rss_excerpt": excerpt,
            }
        )

    return out
