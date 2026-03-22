"""
Environment variables for production (Render) and local development (.env).

Reads use os.environ only — set secrets in the Render dashboard, not in code.
"""

import os


def get_openai_api_key() -> str:
    """OPENAI_API_KEY from the environment; empty string if unset."""
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def require_database_url() -> str:
    """PostgreSQL connection URL from DATABASE_URL (required for this app)."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is required. Set it to your PostgreSQL URL (e.g. on Render)."
        )
    return raw
