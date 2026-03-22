"""
database.py - SQLite setup and CRUD helpers using Python's built-in sqlite3.
No ORM needed for an MVP of this size.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = "news.db"

# Columns inserted on save (no id — AUTOINCREMENT).
# sources / related_links are stored as JSON text (list → string).
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


def get_connection():
    """Returns a new SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def _schema_ok(conn) -> bool:
    """Return True if `news` exists and has every article column."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='news'"
    ).fetchone()
    if not row:
        return False
    col_names = {c[1] for c in conn.execute("PRAGMA table_info(news)").fetchall()}
    return all(c in col_names for c in ARTICLE_COLUMNS)


def init_db():
    """
    Ensure the `news` table exists with the expected columns.

    For local MVP: if the table is missing or wrong, drop and recreate (data is cleared).
    """
    db_abs = os.path.abspath(DB_PATH)
    print(f"[db] using database: {db_abs}")

    with get_connection() as conn:
        if _schema_ok(conn):
            print("[db] news table schema OK")
            return

        print("[db] Recreating news table (simple MVP reset for schema)")
        conn.execute("DROP TABLE IF EXISTS news")
        conn.execute(
            """
            CREATE TABLE news (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                summary         TEXT,
                summary_status  TEXT DEFAULT 'pending',
                source          TEXT,
                source_group    TEXT,
                sources         TEXT,
                related_links   TEXT,
                link            TEXT,
                published       TEXT,
                category        TEXT,
                region          TEXT,
                image_url       TEXT,
                cluster_id      INTEGER,
                trending_score  INTEGER,
                rank_score      REAL,
                rss_excerpt     TEXT,
                last_updated_at TEXT
            )
            """
        )
        conn.commit()
        print("[db] Created news table with all article fields")


def clear_articles() -> None:
    """Delete all articles from the news table."""
    with get_connection() as conn:
        conn.execute("DELETE FROM news")
        conn.commit()


def count_articles() -> int:
    """Total rows in news (for pagination)."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM news").fetchone()
    return int(row[0]) if row else 0


def count_pending_articles() -> int:
    """Rows with summary_status pending (not yet successfully summarized)."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM news
            WHERE summary_status IS NULL
               OR TRIM(COALESCE(summary_status, '')) = ''
               OR LOWER(TRIM(summary_status)) = 'pending'
            """
        ).fetchone()
    return int(row[0]) if row else 0


def get_articles_page(offset: int, limit: int) -> List[Dict]:
    """
    One page of stories ordered for the product feed (rank_score, then id).
    Does not load the full table into memory beyond this page.
    """
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 100))
    cols = ", ".join(READ_COLUMNS)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols} FROM news
            ORDER BY COALESCE(rank_score, 0) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_article_from_row(row) for row in rows]


def get_articles_top(limit: int) -> List[Dict]:
    """Highest-ranked stories (same order as first page of the feed)."""
    limit = max(0, min(int(limit), 10))
    if limit == 0:
        return []
    cols = ", ".join(READ_COLUMNS)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols} FROM news
            ORDER BY COALESCE(rank_score, 0) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_article_from_row(row) for row in rows]


def update_article_summary_fields(
    article_id: int, summary: str, summary_status: str
) -> None:
    """Persist summary + status after lazy generation on a page request."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE news
            SET summary = ?, summary_status = ?, last_updated_at = ?
            WHERE id = ?
            """,
            (summary, summary_status, now, article_id),
        )
        conn.commit()


def _json_list_for_db(value: Any) -> Optional[str]:
    """Turn a Python list (or None) into a JSON string for SQLite TEXT."""
    if value is None:
        return None
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, str):
        # Already stored JSON from elsewhere
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
    """Build a flat dict matching ARTICLE_COLUMNS for executemany."""
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


def _article_from_row(row: sqlite3.Row) -> Dict:
    """Convert a DB row into an article dict with list fields restored."""
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

    cols = ", ".join(ARTICLE_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in ARTICLE_COLUMNS)

    with get_connection() as conn:
        print(f"[db] save_articles input_count={len(prepared)}")
        before = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        conn.executemany(
            f"""
            INSERT INTO news ({cols})
            VALUES ({placeholders})
            """,
            prepared,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        print(f"[db] rows_inserted={after - before}")


def get_articles() -> List[Dict]:
    """
    Return all stored articles (admin / legacy). Ordered like the public feed.
    """
    cols = ", ".join(READ_COLUMNS)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols} FROM news
            ORDER BY COALESCE(rank_score, 0) DESC, id DESC
            """
        ).fetchall()

    result = [_article_from_row(row) for row in rows]
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
