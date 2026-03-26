"""
Load `data/canadian_cities.json` for strong-coverage hints and optional logging metadata.

The dataset is shared with the frontend (same JSON at repo root `data/`).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "canadian_cities.json"


@lru_cache(maxsize=1)
def _dataset_raw() -> Dict[str, Any]:
    if not _DATA_FILE.is_file():
        return {"version": 0, "cities": []}
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def list_cities() -> List[Dict[str, Any]]:
    return list(_dataset_raw().get("cities") or [])


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _key(city: str, province: str) -> Tuple[str, str]:
    return (_norm(city), _norm(province))


@lru_cache(maxsize=1)
def _by_city_province() -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in list_cities():
        c = row.get("city") or ""
        p = row.get("province") or ""
        out[_key(c, p)] = row
    return out


def lookup_location(city: str, province: str) -> Optional[Dict[str, Any]]:
    """Structured record from dataset, or None if unknown."""
    return _by_city_province().get(_key(city, province))


def has_strong_local_coverage(city: str, province: str) -> bool:
    """
    True when the city is marked strong_local_coverage in the dataset
    (registry-style metro anchors) — safe to attach dynamic city RSS patterns.
    """
    row = lookup_location(city, province)
    if not row:
        return False
    return bool(row.get("strong_local_coverage"))


def location_meta_for_log(city: str, province: str) -> Dict[str, Any]:
    """Compact dict for server logs."""
    row = lookup_location(city, province)
    if not row:
        return {
            "city": city,
            "province": province,
            "province_code": None,
            "slug": None,
            "strong_local_coverage": False,
            "in_dataset": False,
        }
    return {
        "city": row.get("city"),
        "province": row.get("province"),
        "province_code": row.get("province_code"),
        "slug": row.get("slug"),
        "strong_local_coverage": bool(row.get("strong_local_coverage")),
        "in_dataset": True,
    }
