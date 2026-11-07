"""Download curated public data indexes and build the sourced mission catalog."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from generate_missions_kb import build as build_missions


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data_kb"
GITHUB_API = "https://api.github.com/repos"
RAW = "https://raw.githubusercontent.com"
USER_AGENT = "GTA-AI-Copilot-KB/1.0"


def get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repo_info(name: str) -> dict[str, Any]:
    info = get_json(f"{GITHUB_API}/{name}")
    commit = get_json(f"{GITHUB_API}/{name}/commits/{info['default_branch']}")
    return {
        "repository": info["full_name"],
        "url": info["html_url"],
        "default_branch": info["default_branch"],
        "license_spdx": (info.get("license") or {}).get("spdx_id"),
        "license_status": "declared" if info.get("license") else "no_license_file_detected",
        "commit": commit["sha"],
    }


def raw_json(owner: str, repo: str, branch: str, path: str) -> Any:
    url = f"{RAW}/{owner}/{repo}/{branch}/{path}"
    return get_json(url)


def build_entity_catalog(dump_info: dict[str, Any]) -> dict[str, int]:
    owner, repo = "DurtyFree", "gta-v-data-dumps"
    branch = dump_info["default_branch"]
    vehicles = raw_json(owner, repo, branch, "vehicles.json")
    weapons = raw_json(owner, repo, branch, "weapons.json")
    zones = raw_json(owner, repo, branch, "zones.json")

    vehicle_rows = []
    for row in vehicles:
        label = row.get("DisplayName") or row.get("TranslatedLabel") or {}
        vehicle_rows.append({
            "model": row.get("Name"),
            "hash": label.get("Hash", row.get("Hash")),
            "label": {key: value for key, value in label.items() if key in {"English", "Chinese", "ChineseTraditional", "ChineseSimplified", "Name"}},
            "manufacturer": row.get("Manufacturer"),
            "class": row.get("Class"),
            "type": row.get("Type"),
        })

    weapon_rows = []
    for row in weapons:
        label = row.get("TranslatedLabel") or row.get("DisplayName") or {}
        weapon_rows.append({
            "name": row.get("Name"),
            "hash": row.get("Hash", label.get("Hash")),
            "label": {key: value for key, value in label.items() if key in {"English", "Chinese", "ChineseTraditional", "ChineseSimplified", "Name"}},
        })

    zone_rows = []
    for row in zones:
        bounds = row.get("Bounds") or []
        zone_rows.append({
            "name": row.get("Name"),
            "display_name": row.get("DisplayName"),
            "bounds": bounds,
        })

    result = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {"repository": "DurtyFree/gta-v-data-dumps", "url": "https://github.com/DurtyFree/gta-v-data-dumps", "license": None},
        "note": "Curated field projection of upstream dumps. Upstream repository has no declared license; check its current terms before redistribution.",
        "vehicles": vehicle_rows,
        "weapons": weapon_rows,
        "zones": zone_rows,
    }
    write_json(DATA_DIR / "entity_catalog.json", result)
    return {"vehicles": len(vehicle_rows), "weapons": len(weapon_rows), "zones": len(zone_rows)}


def build_collectibles_map(map_info: dict[str, Any]) -> dict[str, int]:
    raw = raw_json("danharper", "GTAV", map_info["default_branch"], "locations.json")
    locations = []
    counts: dict[str, int] = {}
    for row in raw:
        kind = str(row.get("type", "Unknown"))
        counts[kind] = counts.get(kind, 0) + 1
        locations.append({key: row[key] for key in ("id", "type", "title", "lat", "lng", "notes", "order") if key in row})
    output = {
        "schema_version": 1,
        "coordinate_system": "danharper_GTAV_Google_Maps_LatLng; not GTA world X/Y/Z",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {"repository": "danharper/GTAV", "url": "https://github.com/danharper/GTAV", "license": "WTFPL"},
        "locations": locations,
        "counts_by_type": counts,
    }
    write_json(DATA_DIR / "collectibles_map.json", output)
    return counts


def build_script_catalog(source: dict[str, Any]) -> int:
    owner, repo = "root-cause", "v-decompiled-scripts"
    tree_url = f"{GITHUB_API}/{owner}/{repo}/git/trees/{source['default_branch']}?recursive=1"
    tree = get_json(tree_url)
    source["commit"] = tree.get("sha")
    names = sorted({Path(item["path"]).stem for item in tree.get("tree", [])
                    if item.get("type") == "blob" and item["path"].lower().endswith(".c")})
    result = {
        "schema_version": 1,
        "source": {"repository": source["repository"], "url": source["url"], "commit": source["commit"], "license": None},
        "note": "Filename-only script index; no decompiled source text is redistributed.",
        "scripts": names,
    }
    write_json(DATA_DIR / "mission_script_catalog.json", result)
    return len(names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-missions", action="store_true", help="Do not call the GTA Wiki API for mission pages")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    dumps = repo_info("DurtyFree/gta-v-data-dumps")
    danharper = repo_info("danharper/GTAV")
    decompiled = repo_info("root-cause/v-decompiled-scripts")
    output_counts = {
        "entity_catalog": build_entity_catalog(dumps),
        "collectibles_map_by_type": build_collectibles_map(danharper),
        "mission_script_filenames": build_script_catalog(decompiled),
    }
    if not args.skip_missions:
        missions = build_missions(workers=max(1, min(args.workers, 10)))
        output_counts["mission_catalog"] = missions["source_counts"]

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": [
            {"repository": "GTA Wiki", "url": "https://gta.fandom.com/wiki/Missions_in_GTA_V", "license": "CC BY-SA", "used_for": "Mission catalog, walkthroughs, gold medal criteria"},
            dumps,
            danharper,
            decompiled,
            {"repository": "Foxxite/GTAV-Geo-Json", "url": "https://github.com/Foxxite/GTAV-Geo-Json", "license_status": "no_license_file_detected", "used_for": "Candidate map geometry source; not imported until game-coordinate conversion is verified"},
        ],
        "output_counts": output_counts,
        "policy": "The source list may include unlicensed repositories. Do not redistribute their payloads without checking their current license terms.",
    }
    write_json(DATA_DIR / "sources_manifest.json", manifest)
    print(json.dumps(output_counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
