"""JARVIS side panel: telemetry, tactical radar, medal list and Alt+Q analysis."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from capture_and_telemetry import capture_screen_base64
from deepseek_client import stream_multimodal
from data_kb.rag_retriever import get_tactical_context


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
TEMP = Path(tempfile.gettempdir())
TELEMETRY = TEMP / "gtav_ai_telemetry.json"
POIS = ROOT / "data_kb" / "world_pois.json"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class Signals(QObject):
    result = Signal(str)


class Radar(QWidget):
    def __init__(self, telemetry_reader) -> None:
        super().__init__()
        self.telemetry_reader = telemetry_reader
        self.setMinimumHeight(235)

    def paintEvent(self, _event) -> None:
        data = self.telemetry_reader()
        loc = data.get("location") or {}
        try:
            px, py = float(loc["x"]), float(loc["y"])
        except (KeyError, TypeError, ValueError):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, radius = self.width() / 2, self.height() / 2, min(self.width(), self.height()) * 0.43
        painter.setPen(QPen(QColor("#41564f"), 1))
        painter.setBrush(QColor(14, 25, 23, 210))
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))
        for ring in (100, 200, 300):
            r = radius * ring / 300
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        for poi in read_json(POIS).get("pois", []):
            try:
                dx, dy = float(poi["x"]) - px, float(poi["y"]) - py
            except (KeyError, TypeError, ValueError):
                continue
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > 300:
                continue
            sx, sy = cx + dx / 300 * radius, cy - dy / 300 * radius
            category = poi.get("category", "")
            color = "#65efc8" if category == "health_soda_machine" else "#ffbf69" if category == "weapon_shop" else "#84b9ff"
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(int(sx - 3), int(sy - 3), 6, 6)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(cx - 5), int(cy - 5), 10, 10)
        painter.setPen(QPen(QColor("#8b9f96"), 1))
        painter.drawText(8, 18, "300 m  |  Soda · Services · POIs")


class CockpitPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        env_file = ROOT.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
        self.signals = Signals()
        self.signals.result.connect(self.show_result)
        self.setWindowTitle("JARVIS Tactical Cockpit")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(QApplication.primaryScreen().availableGeometry().right() - 390, 70, 370, 800)
        self.setStyleSheet("QWidget{background:#101719;color:#e4f0ea;font:10pt 'Segoe UI';} QLabel{padding:5px;} QPlainTextEdit{background:#182421;border:1px solid #30443e;padding:8px;}")
        self.status = QLabel("Waiting for telemetry")
        self.radar = Radar(read_json_telemetry)
        self.advice = QPlainTextEdit("Alt+Q: screenshot and tactical analysis")
        self.advice.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.radar)
        layout.addWidget(QLabel("Mission Gold Checklist"))
        self.checklist = QPlainTextEdit()
        self.checklist.setMaximumHeight(180)
        self.checklist.setReadOnly(True)
        layout.addWidget(self.checklist)
        layout.addWidget(QLabel("Tactical Advice"))
        layout.addWidget(self.advice, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)
        self.register_hotkey()

    def register_hotkey(self) -> None:
        self.hotkey = False
        if os.name == "nt":
            self.hotkey = bool(ctypes_register_hotkey())
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self.poll_hotkey)
        self.hotkey_timer.start(50)

    def poll_hotkey(self) -> None:
        if os.name == "nt" and ctypes_poll_hotkey():
            self.request_analysis()

    def refresh(self) -> None:
        data = read_json_telemetry()
        status = data.get("player_status") or {}
        self.status.setText(f"{data.get('protagonist', '?')} · {data.get('active_mission_script', 'freeroam')}\nHP {status.get('hp', '?')}  Armor {status.get('armor', '?')}  Wanted {status.get('wanted_level', '?')}")
        mission = get_tactical_context(data).get("mission", {}) if data else {}
        criteria = mission.get("gold_medal_criteria", mission.get("gold_medal_requirements", []))
        self.checklist.setPlainText("\n".join(f"☐ {item.get('name', 'Objective')}: {item.get('condition', '')}" for item in criteria) or "No sourced medal checklist for current activity.")
        self.radar.update()

    def request_analysis(self) -> None:
        data = read_json_telemetry()
        if not data:
            self.show_result("Telemetry is unavailable.")
            return
        self.advice.setPlainText("Analyzing screenshot…")
        threading.Thread(target=self.analyze, args=(data,), daemon=True).start()

    def analyze(self, telemetry: dict) -> None:
        try:
            context = get_tactical_context(telemetry)
            screenshot = capture_screen_base64()
            text = "".join(stream_multimodal("Give concise GTA V tactical guidance. Distinguish observed facts from uncertainty.", {"telemetry": telemetry, "tactical_context": context}, screenshot))
            self.signals.result.emit(text)
            if os.environ.get("GTAV_TTS", "1") == "1":
                threading.Thread(target=speak, args=(text[:400],), daemon=True).start()
        except Exception as exc:
            self.signals.result.emit(f"Analysis failed: {exc}")

    def show_result(self, text: str) -> None:
        self.advice.setPlainText(text)

    def closeEvent(self, event) -> None:
        if self.hotkey:
            ctypes_unregister_hotkey()
        super().closeEvent(event)


def read_json_telemetry() -> dict:
    return read_json(TELEMETRY)


def speak(text: str) -> None:
    try:
        import edge_tts
        import winsound
        output = TEMP / "gtav_tts.mp3"
        asyncio.run(edge_tts.Communicate(text, "zh-CN-YunxiNeural").save(str(output)))
        winsound.PlaySound(str(output), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def ctypes_register_hotkey() -> bool:
    import ctypes
    return bool(ctypes.windll.user32.RegisterHotKey(None, 0x47544A, 0x0001, 0x51))


def ctypes_poll_hotkey() -> bool:
    import ctypes
    import ctypes.wintypes
    message = ctypes.wintypes.MSG()
    return bool(ctypes.windll.user32.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1)
                and message.wParam == 0x47544A)


def ctypes_unregister_hotkey() -> None:
    import ctypes
    ctypes.windll.user32.UnregisterHotKey(None, 0x47544A)

