"""
main.py - FastAPI entry point for the Canadian News App
Exposes GET /news which returns summarized news from Canadian RSS feeds.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before other imports (OPENAI_API_KEY, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import (
    count_articles,
    get_articles_page,
    get_articles_top,
    init_db,
    save_news_items,
)
from services.fetch_news import fetch_all_feeds
from services.page_summaries import fill_pending_summaries
from services.ranking import compute_rank_score
from services.story_clustering import cluster_articles
from services.summarize import quick_fallback_summary

PAGE_SIZE = 10
TOP_STORIES_LIMIT = 3

# Public JSON shape for /news (no internal DB-only fields).
_ARTICLE_PUBLIC_KEYS = (
    "id",
    "title",
    "summary",
    "source",
    "link",
    "published",
    "category",
    "region",
    "image_url",
    "sources",
    "related_links",
    "cluster_id",
)


def _public_article(row: dict) -> dict:
    return {k: row.get(k) for k in _ARTICLE_PUBLIC_KEYS}


app = FastAPI(title="Canada Brief API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


@app.on_event("startup")
def startup():
    init_db()


def _strip_rss_excerpt(row: dict) -> None:
    row.pop("rss_excerpt", None)


def _ensure_summary_fallback(row: dict) -> None:
    s = (row.get("summary") or "").strip()
    if s:
        return
    row["summary"] = quick_fallback_summary(row.get("title") or "")


def _run_ingest() -> tuple[int, int, int]:
    t0 = time.time()
    raw_items = fetch_all_feeds()
    n_ingress = len(raw_items)
    clustered = cluster_articles(raw_items)
    n_cluster = len(clustered)
    now = datetime.now(timezone.utc).isoformat()
    for row in clustered:
        row["summary"] = quick_fallback_summary(row.get("title") or "")
        row["summary_status"] = "pending"
        row["rank_score"] = compute_rank_score(row)
        row["last_updated_at"] = now
        ex = row.get("rss_excerpt") or ""
        row["rss_excerpt"] = str(ex)[:12000]
    save_news_items(clustered)
    print(
        f"[/news] ingest done: ingress_to_cluster={n_ingress} "
        f"clusters_saved={n_cluster} time={time.time() - t0:.3f}s"
    )
    return n_ingress, n_cluster, n_cluster


@app.get("/news")
def get_news(
    refresh: bool = False,
    page: int = 1,
    page_size: int = PAGE_SIZE,
):
    """
    Paginated feed: JSON object with "articles" and "top_stories".
    """
    t_start = time.time()
    page = max(1, int(page))
    page_size = min(PAGE_SIZE, max(1, int(page_size)))

    print(
        f"[/news] refresh={refresh} page={page} page_size={page_size} "
        f"(max={PAGE_SIZE})"
    )

    n_ingress = n_cluster = n_saved = 0

    if refresh:
        print("[/news] refresh mode ON — ingest pipeline")
        try:
            n_ingress, n_cluster, n_saved = _run_ingest()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ingest failed: {e}") from e
    elif count_articles() == 0:
        print("[/news] DB empty — cold-start ingest")
        try:
            n_ingress, n_cluster, n_saved = _run_ingest()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ingest failed: {e}") from e
    else:
        print("[/news] serving from SQLite")

    total = count_articles()
    offset = (page - 1) * page_size

    t_read = time.time()
    page_rows = get_articles_page(offset, page_size)
    top_stories = get_articles_top(TOP_STORIES_LIMIT)
    read_elapsed = time.time() - t_read

    t_lazy = time.time()
    n_summaries = fill_pending_summaries(page_rows)
    page_ids = {r["id"] for r in page_rows if r.get("id") is not None}
    top_extra = [r for r in top_stories if r.get("id") not in page_ids]
    if top_extra:
        n_summaries += fill_pending_summaries(top_extra)
    lazy_elapsed = time.time() - t_lazy

    for row in top_stories:
        _ensure_summary_fallback(row)
        _strip_rss_excerpt(row)

    for row in page_rows:
        _ensure_summary_fallback(row)
        _strip_rss_excerpt(row)

    total_elapsed = time.time() - t_start
    print(
        f"[/news] summary: ingress={n_ingress} clustered_saved={n_saved} "
        f"page_items={len(page_rows)} summaries_generated={n_summaries} "
        f"read={read_elapsed:.3f}s lazy={lazy_elapsed:.3f}s total={total_elapsed:.3f}s"
    )

    payload = {
        "articles": [_public_article(r) for r in page_rows],
        "top_stories": [_public_article(r) for r in top_stories],
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"X-Total-Count": str(total)},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
