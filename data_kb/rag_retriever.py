"""Small, stable retrieval interface for telemetry-aware GTA V guidance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent


def _load_json(name: str) -> dict[str, Any]:
    try:
        value = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def get_tactical_context(telemetry: dict) -> dict:
    """Return matching mission guidance and nearby POIs for one telemetry frame."""
    mission_id = str(telemetry.get("active_mission_script", ""))
    missions = _load_json("missions_kb.json").get("missions", {})
    mission = missions.get(mission_id, {}) if isinstance(missions, dict) else {}

    location = telemetry.get("location") or {}
    try:
        x, y = float(location["x"]), float(location["y"])
    except (KeyError, TypeError, ValueError):
        x = y = None

    matches = []
    pois = _load_json("world_pois.json").get("pois", [])
    if x is not None and isinstance(pois, list):
        for poi in pois:
            if not isinstance(poi, dict):
                continue
            try:
                distance = ((float(poi["x"]) - x) ** 2 + (float(poi["y"]) - y) ** 2) ** 0.5
            except (KeyError, TypeError, ValueError):
                continue
            if distance <= float(poi.get("radius_m", 500)):
                matches.append({**poi, "distance_m": round(distance, 1)})
    matches.sort(key=lambda item: item["distance_m"])
    return {"mission_id": mission_id, "mission": mission, "nearby_pois": matches[:10]}
