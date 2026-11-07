"""Click-through full-screen target reticles from native screen projections."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ScreenHudCanvas(QWidget):
    def __init__(self, telemetry_reader) -> None:
        super().__init__()
        self.telemetry_reader = telemetry_reader
        self.phase = 0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.showFullScreen()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self) -> None:
        self.phase = (self.phase + 1) % 40
        self.update()

    def paintEvent(self, _event) -> None:
        data = self.telemetry_reader()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        for target in data.get("active_objectives", []) or []:
            if not target.get("is_on_screen"):
                continue
            try:
                x = float(target["screen_x"]) * width
                y = float(target["screen_y"]) * height
                distance = float(target.get("distance_m", 0))
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= x <= width and 0 <= y <= height):
                continue
            radius = 22 + self.phase // 4
            color = QColor(83, 243, 208, 220)
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(int(x - radius), int(y - radius), radius * 2, radius * 2)
            painter.drawLine(int(x - radius - 8), int(y), int(x + radius + 8), int(y))
            painter.drawLine(int(x), int(y - radius - 8), int(x), int(y + radius + 8))
            painter.setPen(QPen(QColor(230, 248, 241), 1))
            painter.drawText(int(x + radius + 8), int(y - 8), f"{target.get('name', target.get('role', 'Target'))}")
            painter.drawText(int(x + radius + 8), int(y + 12), f"{distance:.0f} m")

