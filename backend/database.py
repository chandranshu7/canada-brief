"""
database.py — SQLAlchemy: PostgreSQL when DATABASE_URL is set (Render), else SQLite (local dev).

Driver for Postgres: postgresql+psycopg (psycopg3). SQLite uses the built-in driver.

List-like fields (sources, related_links) are stored as JSON text in TEXT columns.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    inspect,
    insert,
    text,
)
from sqlalchemy.engine import Engine

from env import get_database_url

# ---------------------------------------------------------------------------
# Config: DATABASE_URL → PostgreSQL; otherwise news.db (SQLite)
# ---------------------------------------------------------------------------
DB_PATH = "news.db"

# Columns inserted on save (no id — autoincrement / SERIAL).
# sources / related_links are stored as JSON text (list → string), same as SQLite MVP.
ARTICLE_COLUMNS = (
    "title",
    "summary",
    "summary_status",
    "source",
    "source_group",
    "sources",
    "related_links",
    "link",
    "published",
    "category",
    "region",
    "image_url",
    "cluster_id",
    "trending_score",
    "rank_score",
    "rss_excerpt",
    "last_updated_at",
)

# id + article fields for reads (pagination, lazy summary updates).
READ_COLUMNS = ("id",) + ARTICLE_COLUMNS

metadata = MetaData()

# Declarative table used for INSERT and schema creation.
# Postgres: INTEGER + SERIAL-style id; REAL rank_score maps to DOUBLE PRECISION.
news_table = Table(
    "news",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    # Default matches prior SQLite schema; inserts still set this explicitly.
    Column("summary_status", Text, server_default=text("'pending'")),
    Column("source", Text),
    Column("source_group", Text),
    Column("sources", Text),
    Column("related_links", Text),
    Column("link", Text),
    Column("published", Text),
    Column("category", Text),
    Column("region", Text),
    Column("image_url", Text),
    Column("cluster_id", Integer),
    Column("trending_score", Integer),
    Column("rank_score", Float),
    Column("rss_excerpt", Text),
    Column("last_updated_at", Text),
)

_engine: Optional[Engine] = None


def _normalize_database_url(raw: str) -> str:
    """
    Render often provides postgres://… — SQLAlchemy + psycopg3 expects postgresql+psycopg://…
    """
    u = raw.strip()
    if u.startswith("postgres://"):
        return u.replace("postgres://", "postgresql+psycopg://", 1)
    if u.startswith("postgresql://") and not u.startswith("postgresql+psycopg"):
        return u.replace("postgresql://", "postgresql+psycopg://", 1)
    return u


def get_engine() -> Engine:
    """Singleton engine: Postgres from DATABASE_URL, else local SQLite file."""
    global _engine
    if _engine is not None:
        return _engine

    raw = get_database_url()
    if raw:
        url = _normalize_database_url(raw)
        # pool_pre_ping: recover from stale connections (common on managed hosts like Render).
        _engine = create_engine(url, pool_pre_ping=True)
    else:
        abs_path = os.path.abspath(DB_PATH)
        _engine = create_engine(
            f"sqlite:///{abs_path}",
            connect_args={"check_same_thread": False},
        )
    return _engine


def _schema_ok(engine: Engine) -> bool:
    """True if `news` exists and has every article column."""
    insp = inspect(engine)
    if not insp.has_table("news"):
        return False
    col_names = {c["name"] for c in insp.get_columns("news")}
    return all(c in col_names for c in ARTICLE_COLUMNS)


def init_db() -> None:
    """
    Ensure the `news` table exists with the expected columns.

    If the table is missing or incomplete (MVP behavior), drop and recreate — data cleared.
    """
    engine = get_engine()

    if _schema_ok(engine):
        print("[db] news table schema OK")
        return

    print("[db] Recreating news table (simple MVP reset for schema)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS news"))
        metadata.create_all(conn)
    print("[db] Created news table with all article fields")


def clear_articles() -> None:
    """Delete all articles from the news table."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM news"))


def count_articles() -> int:
    """Total rows in news (for pagination)."""
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM news")).scalar_one()
    return int(n)


def count_pending_articles() -> int:
    """Rows with summary_status pending (not yet successfully summarized)."""
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM news
                WHERE summary_status IS NULL
                   OR TRIM(COALESCE(summary_status, '')) = ''
                   OR LOWER(TRIM(summary_status)) = 'pending'
                """
            )
        ).scalar_one()
    return int(n)


def get_articles_page(offset: int, limit: int) -> List[Dict]:
    """
    One page of stories ordered for the product feed (rank_score, then id).
    Does not load the full table into memory beyond this page.
    """
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 100))
    cols = ", ".join(READ_COLUMNS)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news
                ORDER BY COALESCE(rank_score, 0) DESC, id DESC
                LIMIT :lim OFFSET :off
                """
            ),
            {"lim": limit, "off": offset},
        ).mappings().all()
    return [_article_from_row(r) for r in rows]


def get_articles_top(limit: int) -> List[Dict]:
    """Highest-ranked stories (same order as first page of the feed)."""
    limit = max(0, min(int(limit), 10))
    if limit == 0:
        return []
    cols = ", ".join(READ_COLUMNS)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news
                ORDER BY COALESCE(rank_score, 0) DESC, id DESC
                LIMIT :lim
                """
            ),
            {"lim": limit},
        ).mappings().all()
    return [_article_from_row(r) for r in rows]


def update_article_summary_fields(
    article_id: int, summary: str, summary_status: str
) -> None:
    """Persist summary + status after lazy generation on a page request."""
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE news
                SET summary = :summary, summary_status = :summary_status, last_updated_at = :lu
                WHERE id = :id
                """
            ),
            {
                "summary": summary,
                "summary_status": summary_status,
                "lu": now,
                "id": article_id,
            },
        )


def _json_list_for_db(value: Any) -> Optional[str]:
    """Turn a Python list (or None) into a JSON string for TEXT columns."""
    if value is None:
        return None
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            return json.dumps([value])
    return json.dumps(list(value)) if value else json.dumps([])


def _list_from_db(json_text: Optional[str]) -> List:
    """Parse JSON TEXT from DB back into a Python list."""
    if json_text is None or json_text == "":
        return []
    try:
        data = json.loads(json_text)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _article_row_for_insert(a: Dict) -> Dict:
    """Build a flat dict matching ARTICLE_COLUMNS for bulk insert."""
    cid = a.get("cluster_id")
    rs = a.get("rank_score")
    return {
        "title": a.get("title"),
        "summary": a.get("summary"),
        "summary_status": a.get("summary_status") or "pending",
        "source": a.get("source"),
        "source_group": a.get("source_group"),
        "sources": _json_list_for_db(a.get("sources")),
        "related_links": _json_list_for_db(a.get("related_links")),
        "link": a.get("link"),
        "published": a.get("published"),
        "category": a.get("category"),
        "region": a.get("region"),
        "image_url": a.get("image_url"),
        "cluster_id": int(cid) if cid is not None else None,
        "trending_score": int(a["trending_score"])
        if a.get("trending_score") is not None
        else None,
        "rank_score": float(rs) if rs is not None else None,
        "rss_excerpt": a.get("rss_excerpt"),
        "last_updated_at": a.get("last_updated_at"),
    }


def _article_from_row(row: Any) -> Dict:
    """Convert a mapping/row into an article dict with list fields restored."""
    d = dict(row)
    d["sources"] = _list_from_db(d.get("sources"))
    d["related_links"] = _list_from_db(d.get("related_links"))
    if d.get("cluster_id") is not None:
        d["cluster_id"] = int(d["cluster_id"])
    if d.get("trending_score") is not None:
        d["trending_score"] = int(d["trending_score"])
    if d.get("rank_score") is not None:
        d["rank_score"] = float(d["rank_score"])
    return d


def save_articles(articles: List[Dict]) -> None:
    """
    Insert article dicts. List fields are stored as JSON strings in TEXT columns.
    """
    if not articles:
        return

    prepared = []
    for i, a in enumerate(articles):
        if i == 0:
            print(f"[db] saved article keys: {sorted(a.keys())}")
        prepared.append(_article_row_for_insert(a))

    engine = get_engine()
    with engine.begin() as conn:
        print(f"[db] save_articles input_count={len(prepared)}")
        before = conn.execute(text("SELECT COUNT(*) FROM news")).scalar_one()
        # SQLAlchemy 2: list of dicts → bulk insert.
        conn.execute(insert(news_table), prepared)
        after = conn.execute(text("SELECT COUNT(*) FROM news")).scalar_one()
        print(f"[db] rows_inserted={after - before}")


def get_articles() -> List[Dict]:
    """
    Return all stored articles (admin / legacy). Ordered like the public feed.
    """
    cols = ", ".join(READ_COLUMNS)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news
                ORDER BY COALESCE(rank_score, 0) DESC, id DESC
                """
            )
        ).mappings().all()

    result = [_article_from_row(r) for r in rows]
    if result:
        print(f"[db] returned article keys: {sorted(result[0].keys())}")
    print(f"[db] get_articles returned={len(result)}")
    return result


def save_news_items(items: List[Dict]) -> None:
    """Compatibility wrapper: clear then save."""
    clear_articles()
    save_articles(items)


def get_all_news() -> List[Dict]:
    """Compatibility wrapper for get_articles()."""
    return get_articles()
