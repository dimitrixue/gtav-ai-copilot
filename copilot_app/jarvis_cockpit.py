"""Launch the Branch B screen HUD and tactical cockpit panel."""

import sys

from PySide6.QtWidgets import QApplication

from cockpit_panel import CockpitPanel
from screen_hud_canvas import ScreenHudCanvas
from cockpit_panel import read_json_telemetry


def main() -> int:
    app = QApplication(sys.argv)
    panel = CockpitPanel()
    canvas = ScreenHudCanvas(read_json_telemetry)
    panel.show()
    canvas.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
