"""Read the local telemetry stream and capture a compact screen image."""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
from pathlib import Path

import mss
from PIL import Image


TELEMETRY_PATH = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "gtav_ai_telemetry.json"


def read_telemetry() -> dict:
    try:
        value = json.loads(TELEMETRY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def capture_screen_base64(max_size: tuple[int, int] = (1600, 900)) -> str:
    with mss.mss() as capture:
        shot = capture.grab(capture.monitors[0])
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    image.thumbnail(max_size)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=78, optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")
