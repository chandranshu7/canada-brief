"""
database.py — SQLAlchemy: PostgreSQL when DATABASE_URL is set (Render), else SQLite (local dev).

Driver for Postgres: postgresql+psycopg (psycopg3). SQLite uses the built-in driver.

List-like fields (sources, related_links) are stored as JSON text in TEXT columns.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
from sqlalchemy.exc import IntegrityError

from env import get_database_url
from services.feed_dedupe import article_dedupe_key
from services.fetch_news import content_fingerprint_for_dedup, normalize_link

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
    "topic_category",
    "region",
    "coverage_city",
    "coverage_province",
    "coverage_level",
    "feed_registry_key",
    "image_url",
    "video_url",
    "cluster_id",
    "trending_score",
    "rank_score",
    "rss_excerpt",
    "last_updated_at",
)

# id + article fields for reads (pagination, lazy summary updates).
READ_COLUMNS = ("id",) + ARTICLE_COLUMNS

# Local-mode table: same article fields + which (city, province) ingest produced this row.
SCOPE_COLUMNS = ("scope_city", "scope_province")
ARTICLE_COLUMNS_LOCAL = ARTICLE_COLUMNS + SCOPE_COLUMNS
READ_COLUMNS_LOCAL = ("id",) + ARTICLE_COLUMNS_LOCAL

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
    Column("topic_category", Text),
    Column("region", Text),
    Column("coverage_city", Text),
    Column("coverage_province", Text),
    Column("coverage_level", Text),
    Column("feed_registry_key", Text),
    Column("image_url", Text),
    Column("video_url", Text),
    Column("cluster_id", Integer),
    Column("trending_score", Integer),
    Column("rank_score", Float),
    Column("rss_excerpt", Text),
    Column("last_updated_at", Text),
)

news_local_table = Table(
    "news_local",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    Column("summary_status", Text, server_default=text("'pending'")),
    Column("source", Text),
    Column("source_group", Text),
    Column("sources", Text),
    Column("related_links", Text),
    Column("link", Text),
    Column("published", Text),
    Column("category", Text),
    Column("topic_category", Text),
    Column("region", Text),
    Column("coverage_city", Text),
    Column("coverage_province", Text),
    Column("coverage_level", Text),
    Column("feed_registry_key", Text),
    Column("image_url", Text),
    Column("video_url", Text),
    Column("cluster_id", Integer),
    Column("trending_score", Integer),
    Column("rank_score", Float),
    Column("rss_excerpt", Text),
    Column("last_updated_at", Text),
    Column("scope_city", Text, nullable=False),
    Column("scope_province", Text, nullable=False),
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
    """True if `news` and `news_local` exist with every expected column."""
    insp = inspect(engine)
    if not insp.has_table("news") or not insp.has_table("news_local"):
        return False
    news_cols = {c["name"] for c in insp.get_columns("news")}
    local_cols = {c["name"] for c in insp.get_columns("news_local")}
    return all(c in news_cols for c in ARTICLE_COLUMNS) and all(
        c in local_cols for c in ARTICLE_COLUMNS_LOCAL
    )


def _try_unique_news_link_index(conn) -> None:
    """Best-effort UNIQUE(link) — merge ingest assumes no duplicate links."""
    try:
        conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_news_link ON news(link)")
        )
        print("[db] unique index uq_news_link on news(link) ensured")
    except Exception as e:
        print(f"[db] unique index on news(link) skipped (duplicates or backend): {e}")


def _migrate_add_missing_columns(conn) -> None:
    """ALTER TABLE ADD COLUMN for any new fields (e.g. topic_category) without wiping data."""
    insp = inspect(conn)
    for table_name, expected in (
        ("news", ARTICLE_COLUMNS),
        ("news_local", ARTICLE_COLUMNS_LOCAL),
    ):
        if not insp.has_table(table_name):
            continue
        existing = {c["name"] for c in insp.get_columns(table_name)}
        for col in expected:
            if col not in existing:
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT")
                )
                print(f"[db] migrated: {table_name}.{col} added")


def init_db() -> None:
    """
    Ensure `news` (General) and `news_local` (Local) exist with expected columns.

    Creates tables if missing, then adds any new columns via ALTER. If schema is still
    invalid (legacy MVP), drop and recreate — data cleared.
    """
    engine = get_engine()

    with engine.begin() as conn:
        metadata.create_all(conn)
        _migrate_add_missing_columns(conn)
        if inspect(engine).has_table("news"):
            _try_unique_news_link_index(conn)

    if _schema_ok(engine):
        print("[db] news + news_local table schemas OK")
        return

    print("[db] Recreating news + news_local tables (simple MVP reset for schema)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS news_local"))
        conn.execute(text("DROP TABLE IF EXISTS news"))
        metadata.create_all(conn)
        _try_unique_news_link_index(conn)
    print("[db] Created news and news_local tables")


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


def get_news_max_id() -> int:
    """Largest `news.id` (for Daily Brief cache invalidation when new rows are inserted)."""
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COALESCE(MAX(id), 0) AS m FROM news")
        ).scalar_one()
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


def count_local_articles(city: str, province: str) -> int:
    """Rows in news_local for this location scope."""
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return 0
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                """
            ),
            {"c": c, "p": p},
        ).scalar_one()
    return int(n)


def local_scope_max_last_updated(city: str, province: str) -> Optional[str]:
    """Latest `last_updated_at` ISO value for one local scope (or None when empty)."""
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        v = conn.execute(
            text(
                """
                SELECT MAX(last_updated_at) AS m FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                """
            ),
            {"c": c, "p": p},
        ).scalar_one()
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def clear_local_scope(city: str, province: str) -> None:
    """Delete local rows for one city/province before re-ingest."""
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                """
            ),
            {"c": c, "p": p},
        )


def _article_row_for_local_insert(a: Dict) -> Dict:
    """Flat dict for news_local bulk insert."""
    base = _article_row_for_insert(a)
    base["scope_city"] = a.get("scope_city")
    base["scope_province"] = a.get("scope_province")
    return base


def save_local_articles(articles: List[Dict], scope_city: str, scope_province: str) -> None:
    """Insert into news_local (caller clears scope first)."""
    if not articles:
        return
    sc = (scope_city or "").strip()
    sp = (scope_province or "").strip()
    prepared = []
    for i, a in enumerate(articles):
        row = dict(a)
        row["scope_city"] = sc
        row["scope_province"] = sp
        if i == 0:
            print(f"[db] local saved article keys: {sorted(row.keys())}")
        prepared.append(_article_row_for_local_insert(row))

    engine = get_engine()
    with engine.begin() as conn:
        print(f"[db] save_local_articles input_count={len(prepared)} scope={sc!r}/{sp!r}")
        conn.execute(insert(news_local_table), prepared)


def save_local_news_items(
    items: List[Dict], scope_city: str, scope_province: str
) -> None:
    """Replace all rows for this local scope."""
    clear_local_scope(scope_city, scope_province)
    save_local_articles(items, scope_city, scope_province)


def load_local_feed_sorted(
    city: str, province: str, plan: Optional[Any] = None
) -> List[Dict]:
    """
    Local mode: read scoped `news_local` rows → strict locality sort (no unrelated regions).

    Optional `plan` (LocalFeedPlan): reuse feed-selection metadata when the caller already
    built it (avoids double work on /news).
    """
    c = (city or "").strip()
    p = (province or "").strip()
    cols = ", ".join(READ_COLUMNS_LOCAL)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                """
            ),
            {"c": c, "p": p},
        ).mappings().all()
    articles = [_article_from_row(r) for r in rows]
    from services.local_feed import sort_articles_local_mode

    return sort_articles_local_mode(articles, city, province, plan=plan)


def _search_like_pattern(q: str) -> str:
    """LIKE pattern with % / _ / \\ escaped for ESCAPE '\\' (SQLite + PostgreSQL)."""
    raw = (q or "").strip()
    if not raw:
        return ""
    esc = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc.lower()}%"


def _news_search_where_sql() -> str:
    """Substring match across common text columns (case-insensitive)."""
    return """(
      LOWER(COALESCE(title, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(summary, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(region, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(source, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(source_group, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(category, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(topic_category, '')) LIKE :pat ESCAPE '\\' OR
      LOWER(COALESCE(rss_excerpt, '')) LIKE :pat ESCAPE '\\'
    )"""


def count_news_search(q: str) -> int:
    """General table: number of rows matching search."""
    pat = _search_like_pattern(q)
    if not pat:
        return 0
    w = _news_search_where_sql()
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            text(f"SELECT COUNT(*) AS n FROM news WHERE {w}"),
            {"pat": pat},
        ).scalar_one()
    return int(n)


def search_news_page(offset: int, limit: int, q: str) -> List[Dict]:
    """General `news`: paginated search, same order as feed (rank_score DESC, id DESC)."""
    pat = _search_like_pattern(q)
    if not pat:
        return []
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 100))
    cols = ", ".join(READ_COLUMNS)
    w = _news_search_where_sql()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news
                WHERE {w}
                ORDER BY COALESCE(rank_score, 0) DESC, id DESC
                LIMIT :lim OFFSET :off
                """
            ),
            {"pat": pat, "lim": limit, "off": offset},
        ).mappings().all()
    return [_article_from_row(r) for r in rows]


def count_news_local_search(city: str, province: str, q: str) -> int:
    """Scoped `news_local` row count matching search."""
    pat = _search_like_pattern(q)
    if not pat:
        return 0
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return 0
    w = _news_search_where_sql()
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS n FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                  AND {w}
                """
            ),
            {"c": c, "p": p, "pat": pat},
        ).scalar_one()
    return int(n)


def search_news_local_page(
    offset: int, limit: int, city: str, province: str, q: str
) -> List[Dict]:
    """Local scoped table: paginated search."""
    pat = _search_like_pattern(q)
    if not pat:
        return []
    c = (city or "").strip()
    p = (province or "").strip()
    if not c or not p:
        return []
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 100))
    cols = ", ".join(READ_COLUMNS_LOCAL)
    w = _news_search_where_sql()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT {cols} FROM news_local
                WHERE scope_city = :c AND scope_province = :p
                  AND {w}
                ORDER BY COALESCE(rank_score, 0) DESC, id DESC
                LIMIT :lim OFFSET :off
                """
            ),
            {"c": c, "p": p, "pat": pat, "lim": limit, "off": offset},
        ).mappings().all()
    return [_article_from_row(r) for r in rows]


def get_articles_page(
    offset: int,
    limit: int,
) -> List[Dict]:
    """
    One page of stories: rank_score DESC, id DESC (General mode).
    rank_score includes strong recency (see ranking.py), including a boost for the last ~2h.
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
    """Highest-ranked stories (General feed order)."""
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


def update_local_article_summary_fields(
    article_id: int, summary: str, summary_status: str
) -> None:
    """Same as update_article_summary_fields but for `news_local`."""
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE news_local
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
        "topic_category": a.get("topic_category"),
        "region": a.get("region"),
        "coverage_city": a.get("coverage_city"),
        "coverage_province": a.get("coverage_province"),
        "coverage_level": a.get("coverage_level"),
        "feed_registry_key": a.get("feed_registry_key"),
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


def merge_news_articles(items: List[Dict]) -> Tuple[int, Dict[str, Any]]:
    """
    Insert only rows whose normalized `link` is not already in `news`, and whose
    content fingerprint (title + source + published) is not already present.
    Each accepted row is committed immediately (separate transaction) so new stories
    appear without waiting for the full merge batch.
    Returns (inserted_count, diagnostics).
    """
    diag: Dict[str, Any] = {
        "merge_candidates": len(items),
        "merge_skipped_missing_link": 0,
        "merge_skipped_duplicate_db_link": 0,
        "merge_skipped_duplicate_batch_link": 0,
        "merge_skipped_duplicate_db_content_hash": 0,
        "merge_skipped_duplicate_batch_content_hash": 0,
        "merge_skipped_integrity_error": 0,
        "sample_skipped_duplicates": [],
        "sample_new_links": [],
    }
    _cap = 5

    if not items:
        print("[db] merge_news_articles input_count=0")
        return 0, diag

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT link, title, source, published FROM news
                """
            )
        ).fetchall()
    existing_db: set[str] = set()
    existing_fp: set[str] = set()
    for r in rows:
        lk = r[0]
        if lk:
            existing_db.add(normalize_link(str(lk)))
        existing_fp.add(
            content_fingerprint_for_dedup(
                {
                    "title": r[1],
                    "source": r[2],
                    "published": r[3],
                }
            )
        )

    seen_batch: set[str] = set()
    seen_batch_fp: set[str] = set()
    inserted_count = 0
    for a in items:
        row = _article_row_for_insert(a)
        raw_link = (row.get("link") or "").strip()
        if not raw_link:
            diag["merge_skipped_missing_link"] += 1
            if len(diag["sample_skipped_duplicates"]) < _cap:
                diag["sample_skipped_duplicates"].append(
                    {
                        "reason": "missing_required_link",
                        "dedupe_key": repr(article_dedupe_key(a)),
                        "title": (a.get("title") or "")[:120],
                    }
                )
            continue
        nk = normalize_link(raw_link)
        fp = content_fingerprint_for_dedup(a)
        if nk in existing_db:
            diag["merge_skipped_duplicate_db_link"] += 1
            if len(diag["sample_skipped_duplicates"]) < _cap:
                diag["sample_skipped_duplicates"].append(
                    {
                        "reason": "duplicate_normalized_link_in_db",
                        "normalized_link": nk[:220],
                        "dedupe_key": repr(article_dedupe_key(a)),
                        "title": (a.get("title") or "")[:120],
                    }
                )
            continue
        if nk in seen_batch:
            diag["merge_skipped_duplicate_batch_link"] += 1
            if len(diag["sample_skipped_duplicates"]) < _cap:
                diag["sample_skipped_duplicates"].append(
                    {
                        "reason": "duplicate_normalized_link_in_merge_batch",
                        "normalized_link": nk[:220],
                        "dedupe_key": repr(article_dedupe_key(a)),
                        "title": (a.get("title") or "")[:120],
                    }
                )
            continue
        if fp in existing_fp:
            diag["merge_skipped_duplicate_db_content_hash"] += 1
            if len(diag["sample_skipped_duplicates"]) < _cap:
                diag["sample_skipped_duplicates"].append(
                    {
                        "reason": "duplicate_content_fingerprint_in_db",
                        "fingerprint": fp,
                        "title": (a.get("title") or "")[:120],
                    }
                )
            continue
        if fp in seen_batch_fp:
            diag["merge_skipped_duplicate_batch_content_hash"] += 1
            if len(diag["sample_skipped_duplicates"]) < _cap:
                diag["sample_skipped_duplicates"].append(
                    {
                        "reason": "duplicate_content_fingerprint_in_merge_batch",
                        "fingerprint": fp,
                        "title": (a.get("title") or "")[:120],
                    }
                )
            continue
        seen_batch.add(nk)
        seen_batch_fp.add(fp)
        if len(diag["sample_new_links"]) < _cap:
            diag["sample_new_links"].append(
                {
                    "normalized_link": nk[:220],
                    "title": (a.get("title") or "")[:120],
                }
            )
        try:
            with engine.begin() as conn:
                conn.execute(insert(news_table), [row])
        except IntegrityError:
            # Race on unique(link) or duplicate despite pre-check — keep merge safe.
            seen_batch.discard(nk)
            seen_batch_fp.discard(fp)
            diag["merge_skipped_integrity_error"] += 1
            continue
        inserted_count += 1
        existing_db.add(nk)
        existing_fp.add(fp)

    print(
        f"[db] merge_news_articles candidates={diag['merge_candidates']} "
        f"skipped_missing_link={diag['merge_skipped_missing_link']} "
        f"skipped_dup_db={diag['merge_skipped_duplicate_db_link']} "
        f"skipped_dup_batch={diag['merge_skipped_duplicate_batch_link']} "
        f"skipped_dup_db_fp={diag['merge_skipped_duplicate_db_content_hash']} "
        f"skipped_dup_batch_fp={diag['merge_skipped_duplicate_batch_content_hash']} "
        f"skipped_integrity={diag['merge_skipped_integrity_error']} "
        f"inserted={inserted_count}"
    )
    print(
        f"[db] [ingest_diag_merge] sample_skipped={diag['sample_skipped_duplicates']} "
        f"sample_new={diag['sample_new_links']}"
    )

    return inserted_count, diag


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
