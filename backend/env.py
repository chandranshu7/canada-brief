"""
Environment variables for production (Render) and local development (.env).

Reads use os.environ only — set secrets in the Render dashboard, not in code.
"""

import os


def get_openai_api_key() -> str:
    """OPENAI_API_KEY from the environment; empty string if unset."""
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def get_database_url() -> str:
    """
    DATABASE_URL if set (e.g. Render Postgres). Empty string if unset.

    When unset, database.py falls back to local SQLite (news.db) for development.
    """
    return (os.environ.get("DATABASE_URL") or "").strip()
