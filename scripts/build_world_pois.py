"""Build native GTA world-coordinate POIs and merge optional game exports."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_kb" / "world_pois.json"
BASE = "https://raw.githubusercontent.com/DurtyFree/gta-v-data-dumps/master/"
SOURCES = {
    "mloInteriors.json": "interior",
    "garages.json": "garage",
    "objectslocations/worldVendingMachines.json": "health_soda_machine",
    "objectslocations/worldGasPumps.json": "gas_station",
}
HEADERS = {"User-Agent": "GTA-AI-Copilot-KB/1.0"}


def fetch(path: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(BASE + path, headers=HEADERS)
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                value = json.load(response)
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    else:
        raise last_error
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON array from {path}")
    return value


def point(name: str, kind: str, position: dict[str, Any], source: str, **extra: Any) -> dict[str, Any] | None:
    try:
        x, y, z = (float(position[key]) for key in ("X", "Y", "Z"))
    except (KeyError, TypeError, ValueError):
        return None
    record_index = extra.get("record_index", "")
    return {"id": f"{kind}:{source}:{record_index}:{name}", "name": name, "category": kind,
            "x": x, "y": y, "z": z, "source": source, **extra}


def upstream_points() -> list[dict[str, Any]]:
    result = []
    interiors = fetch("mloInteriors.json")
    for interior in interiors:
        locations = interior.get("Locations") or []
        for index, location in enumerate(locations):
            item = point(interior.get("Name", "unknown"), "interior", location.get("Position") or "",
                         "DurtyFree/gta-v-data-dumps:mloInteriors.json",
                         interior_id=location.get("InteriorId"), file_path=location.get("FilePath"), location_index=index,
                         record_index=f"{interior.get('Name')}:{index}")
            if item:
                result.append(item)
    for path, category in list(SOURCES.items())[1:]:
        for index, row in enumerate(fetch(path)):
            item = point(row.get("Name", f"{category}_{index}"), category, row.get("Position") or "",
                         f"DurtyFree/gta-v-data-dumps:{path}", rotation=row.get("Rotation"), record_index=index)
            if item:
                result.append(item)
    return result


def engine_points(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("pois", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        coords = row.get("position", row)
        item = point(str(row.get("name") or f"blip_{index}"), str(row.get("category") or "engine_static_blip"),
                     {"X": coords.get("x", coords.get("X")), "Y": coords.get("y", coords.get("Y")), "Z": coords.get("z", coords.get("Z"))},
                     "GTA V engine World.GetAllBlips", sprite=row.get("sprite"), blip_name=row.get("name"), record_index=index)
        if item:
            result.append(item)
    return result


def build(engine_path: Path, output: Path = OUT) -> dict[str, Any]:
    upstream = upstream_points()
    engine = engine_points(engine_path)
    by_id = {item["id"]: item for item in upstream}
    for item in engine:
        by_id[item["id"]] = item
    pois = list(by_id.values())
    payload = {
        "schema_version": 2,
        "coordinate_system": "GTA V world coordinates (meters), X/Y/Z",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": [
            {"repository": "DurtyFree/gta-v-data-dumps", "url": "https://github.com/DurtyFree/gta-v-data-dumps", "license": None},
            {"source": "GTA V engine World.GetAllBlips", "file": str(engine_path)},
        ],
        "counts": {"upstream_native_points": len(upstream), "engine_blips": len(engine), "total": len(pois)},
        "pois": pois,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-export", type=Path,
                        default=Path(__import__("tempfile").gettempdir()) / "gtav_engine_static_pois.json")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    payload = build(args.engine_export, args.output)
    print(json.dumps(payload["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
