"""
story_clustering.py

Groups RSS articles that describe the same news story into *clusters*.

Why embeddings?
  Title + summary text is turned into vectors. Stories about the same event
  usually land close together in that space, even when headlines use different
  wording (better than plain keyword overlap).

When OpenAI is not configured:
  We fall back to TF-IDF + the same hierarchical clustering (fast, local, free).

Performance:
  Clustering runs only after a refresh fetch (see main.py), never on cached reads.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import numpy as np
import requests
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize as sk_normalize

# --- OpenAI embeddings (optional) --------------------------------------------
# API key: same OPENAI_API_KEY as summarizer; never hardcode secrets.
_DEFAULT_EMBED_MODEL = "text-embedding-3-small"
# Cosine-related distance on L2-normalized embeddings; lower = stricter (smaller clusters).
_DEFAULT_EMBED_DISTANCE = 0.48
# TF-IDF fallback: distance on unit vectors (same Agglomerative setup as before).
_DEFAULT_TFIDF_DISTANCE = 1.2


def _cluster_text_for_vector(article: Dict) -> str:
    """One string per article: title + summary so the model sees real content."""
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    if summary:
        return f"{title}\n{summary}"[:8000]
    return title or "untitled"


def _fetch_openai_embeddings(texts: List[str]) -> np.ndarray:
    """
    Batch embedding call. Raises on HTTP/API errors (caller falls back to TF-IDF).
    """
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


def _labels_from_vectors(X: np.ndarray, distance_threshold: float) -> np.ndarray:
    """Hierarchical clustering on L2-normalized rows (n x d)."""
    n = X.shape[0]
    if n == 1:
        return np.array([0], dtype=int)
    Xn = sk_normalize(X, norm="l2")
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="euclidean",
        linkage="average",
    )
    return clustering.fit_predict(Xn)


def _labels_tfidf(titles: List[str], distance_threshold: float) -> np.ndarray:
    """Local fallback: TF-IDF bag-of-words on titles only."""
    n = len(titles)
    if n == 1:
        return np.array([0], dtype=int)
    vectorizer = TfidfVectorizer(max_df=0.95, min_df=1, stop_words="english")
    X = vectorizer.fit_transform(titles)
    Xn = sk_normalize(X.toarray(), norm="l2")
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="euclidean",
        linkage="average",
    )
    return clustering.fit_predict(Xn)


def cluster_articles(articles: List[Dict]) -> List[Dict]:
    """
    Cluster articles, then collapse each cluster to *one* main row.

    - cluster_id: integer label from clustering (same value = same story group).
    - sources: distinct outlet names in the cluster ("Also reported by:" in the UI).
    - related_links: other article URLs in the cluster.
    - trending_score: number of articles in the cluster (more coverage → higher).

    Does not mutate the input list.
    """
    if not articles:
        return []

    n = len(articles)
    titles = [(a.get("title") or "").strip() or "untitled" for a in articles]
    texts = [_cluster_text_for_vector(a) for a in articles]

    used_embeddings = False
    labels: np.ndarray

    embed_threshold = float(
        os.environ.get("CLUSTER_EMBED_DISTANCE", str(_DEFAULT_EMBED_DISTANCE))
    )
    tfidf_threshold = float(
        os.environ.get("CLUSTER_TFIDF_DISTANCE", str(_DEFAULT_TFIDF_DISTANCE))
    )

    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        try:
            X = _fetch_openai_embeddings(texts)
            labels = _labels_from_vectors(X, embed_threshold)
            used_embeddings = True
            print(
                f"[cluster] mode=openai_embeddings model="
                f"{(os.environ.get('OPENAI_EMBEDDING_MODEL') or _DEFAULT_EMBED_MODEL).strip()} "
                f"threshold={embed_threshold}"
            )
        except Exception as e:
            print(f"[cluster] embeddings failed ({e}); fallback=tfidf_titles")
            labels = _labels_tfidf(titles, tfidf_threshold)
    else:
        print("[cluster] mode=tfidf_titles (no OPENAI_API_KEY)")
        labels = _labels_tfidf(titles, tfidf_threshold)

    by_cluster: Dict[int, List[Dict]] = defaultdict(list)
    for i, lab in enumerate(labels):
        by_cluster[int(lab)].append(articles[i])

    print(
        f"[cluster] total_clusters={len(by_cluster)} "
        f"vector_backend={'embeddings' if used_embeddings else 'tfidf'}"
    )
    for cid in sorted(by_cluster.keys()):
        members = by_cluster[cid]
        print(f"[cluster] cluster_id={cid} size={len(members)}")

    if by_cluster:
        singletons = sum(1 for m in by_cluster.values() if len(m) == 1)
        total_c = len(by_cluster)
        if total_c > 0 and singletons / total_c > 0.95:
            print(
                f"[cluster] WARN clustering ineffective: {singletons}/{total_c} "
                f"clusters are singletons (>95%); consider tuning distance thresholds"
            )

    out: List[Dict] = []
    for cid in sorted(by_cluster.keys()):
        cl = by_cluster[cid]
        trending_score = len(cl)

        # Main row = most recently published article in the cluster (best "breaking" pick).
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
        out.append(
            {
                "title": main.get("title"),
                "summary": main.get("summary"),
                "source": main.get("source"),
                "source_group": main.get("source_group"),
                "sources": sources,
                "link": main_link,
                "related_links": related_links,
                "published": main.get("published"),
                "category": main.get("category"),
                "region": main.get("region"),
                "image_url": main.get("image_url"),
                "cluster_id": cid,
                "trending_score": trending_score,
                "rss_excerpt": excerpt,
            }
        )

    # Final feed order is decided by rank_score when saving to SQLite.
    return out
