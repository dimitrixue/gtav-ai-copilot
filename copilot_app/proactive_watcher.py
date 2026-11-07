"""Event-driven tactical advice and in-game marker command writer (Branch A)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from capture_and_telemetry import TELEMETRY_PATH, capture_screen_base64
from deepseek_client import stream_multimodal


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from data_kb.rag_retriever import get_tactical_context

POI_PATH = ROOT / "data_kb" / "world_pois.json"
COMMAND_PATH = Path(tempfile.gettempdir()) / "gtav_ai_commands.json"
EVENT_COOLDOWN = 15.0


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_commands(markers: list[dict], notification: str) -> None:
    payload = {
        "expires_at": int(time.time() * 1000) + 12_000,
        "draw_3d_markers": markers[:8],
        "in_game_notification": notification[:240],
    }
    temporary = COMMAND_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, COMMAND_PATH)


def nearest_supply(telemetry: dict) -> dict | None:
    location = telemetry.get("location") or {}
    try:
        x, y = float(location["x"]), float(location["y"])
    except (KeyError, TypeError, ValueError):
        return None
    pois = read_json(POI_PATH).get("pois", [])
    candidates = [p for p in pois if p.get("category") in {"health_soda_machine", "weapon_shop", "safehouse"}]
    if not candidates:
        return None
    return min(candidates, key=lambda p: (float(p["x"]) - x) ** 2 + (float(p["y"]) - y) ** 2)


def objective_markers(telemetry: dict, trigger: str) -> list[dict]:
    targets = telemetry.get("active_objectives") or []
    if trigger in {"low_hp", "wanted"}:
        supply = nearest_supply(telemetry)
        if supply:
            targets = [supply]
    markers = []
    for target in targets[:3]:
        try:
            markers.append({
                "x": float(target["x"]), "y": float(target["y"]), "z": float(target.get("z", 0)),
                "label": str(target.get("name") or target.get("role") or "Tactical target"),
                "draw_line_from_player": True, "color": [0, 255, 200, 180],
            })
        except (KeyError, TypeError, ValueError):
            continue
    return markers


def classify_event(current: dict, previous: dict) -> str | None:
    mission = str(current.get("active_mission_script", "freeroam"))
    old_mission = str(previous.get("active_mission_script", "freeroam"))
    if mission not in {"", "freeroam", "unknown"} and mission != old_mission:
        return "mission_start"
    objectives = current.get("active_objectives") or []
    old_objectives = previous.get("active_objectives") or []
    if objectives and old_objectives:
        a, b = objectives[0], old_objectives[0]
        try:
            moved = ((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5
            if moved > 50:
                return "objective_change"
        except (KeyError, TypeError, ValueError):
            pass
    status = current.get("player_status") or {}
    try:
        if int(status.get("hp", 999)) < 40:
            return "low_hp"
        if int(status.get("wanted_level", 0)) >= 3:
            return "wanted"
    except (TypeError, ValueError):
        pass
    return None


def advise(telemetry: dict, event: str) -> str:
    env_file = ROOT.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    context = get_tactical_context(telemetry)
    prompt = (
        "You are an event-driven GTA V Story Mode tactical advisor. "
        f"Trigger={event}. Give concise next actions, medal warnings, and uncertainty. "
        "Coordinates and locations must come only from the supplied context."
    )
    screen = capture_screen_base64()
    return "".join(stream_multimodal(prompt, {"telemetry": telemetry, "tactical_context": context}, screen))


def run() -> None:
    previous: dict = {}
    last_trigger = 0.0
    while True:
        current = read_json(TELEMETRY_PATH)
        event = classify_event(current, previous) if current else None
        now = time.monotonic()
        if event and now - last_trigger >= EVENT_COOLDOWN:
            try:
                advice = advise(current, event)
                notification = advice[:200] or f"Tactical event: {event}"
            except Exception as exc:
                notification = f"Tactical analysis unavailable: {exc}"[:200]
            write_commands(objective_markers(current, event), notification)
            last_trigger = now
        previous = current
        time.sleep(0.25)


if __name__ == "__main__":
    run()
