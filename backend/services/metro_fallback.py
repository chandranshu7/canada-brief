"""
Map user-selected cities that lack dedicated RSS anchors to a nearby metro hub.

Used by Local mode: ingest hub city feeds + classify hub-tagged stories as metro tier
before province and national.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

# Normalized city key -> hub display name (must match source_registry metro `city` fields).
_CITY_TO_METRO_HUB: Dict[str, str] = {
    "brampton": "Toronto",
    "mississauga": "Toronto",
    "markham": "Toronto",
    "vaughan": "Toronto",
    "oakville": "Toronto",
    "richmondhill": "Toronto",
    "pickering": "Toronto",
    "ajax": "Toronto",
    "oshawa": "Toronto",
    "laval": "Montreal",
    "longueuil": "Montreal",
    "gatineau": "Ottawa",
    "surrey": "Vancouver",
    "coquitlam": "Vancouver",
}


def _norm_city_key(city: str) -> str:
    return re.sub(r"[^a-z]+", "", (city or "").strip().lower())


def metro_hub_for_city(city: str) -> Optional[str]:
    """
    Return the metro hub display name for nearby regional feeds, or None if no mapping.

    If the selected city is already the hub (or unknown), returns None so callers do not
    duplicate hub feeds.
    """
    raw = (city or "").strip()
    if not raw:
        return None
    key = _norm_city_key(raw)
    if not key:
        return None
    hub = _CITY_TO_METRO_HUB.get(key)
    if not hub:
        return None
    if hub.strip().lower() == raw.lower():
        return None
    return hub
