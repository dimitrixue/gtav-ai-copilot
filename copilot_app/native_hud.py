"""Compact native-style tactical status HUD for Branch A."""

from __future__ import annotations

import json
import tempfile
import tkinter as tk
from pathlib import Path


TELEMETRY = Path(tempfile.gettempdir()) / "gtav_ai_telemetry.json"


class NativeHud:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("GTA Tactical HUD")
        self.root.geometry("330x150+20+80")
        self.root.configure(bg="#101719")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)
        self.label = tk.Label(self.root, text="Waiting for telemetry", bg="#101719", fg="#d7eee5",
                              justify="left", anchor="nw", font=("Segoe UI", 10), padx=12, pady=10)
        self.label.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        try:
            data = json.loads(TELEMETRY.read_text(encoding="utf-8-sig"))
            status = data.get("player_status", {})
            self.label.configure(text=(
                f"{data.get('protagonist', '?')}  |  {data.get('active_mission_script', 'freeroam')}\n"
                f"HP {status.get('hp', '?')}   Armor {status.get('armor', '?')}   Wanted {status.get('wanted_level', '?')}\n"
                f"{(data.get('location') or {}).get('zone_name', 'Unknown location')}\n"
                "AI event advice is sent to the in-game command channel."
            ))
        except (OSError, json.JSONDecodeError):
            self.label.configure(text="Waiting for telemetry")
        self.root.after(250, self.refresh)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    NativeHud().run()
