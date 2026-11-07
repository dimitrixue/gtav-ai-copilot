from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import io
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Frame, Label, Text, Tk

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import mss
except ImportError:
    mss = None


ROOT = Path(__file__).resolve().parent
TELEMETRY_PATH = Path(os.environ.get("TEMP", Path.home() / "AppData/Local/Temp")) / "gtav_ai_telemetry.json"
KB_PATH = ROOT.parent / "data_kb" / "missions_kb.json"
ENV_PATH = ROOT.parent / ".env"
API_URL = "https://api.deepseek.com/chat/completions"
HOTKEY_ID = 0x475441
MOD_ALT = 0x0001
VK_Q = 0x51


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def format_num(value: object, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "?"


class Overlay:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("GTA V AI 战术助手")
        self.root.geometry("420x520")
        self.root.minsize(420, 520)
        self.root.maxsize(420, 520)
        self.root.configure(bg="#101416")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.82)
        self.root.overrideredirect(True)
        self.root.update_idletasks()
        self.root.geometry(f"420x520+{self.root.winfo_screenwidth() - 440}+24")
        self.root.bind("<ButtonPress-1>", self.drag_start)
        self.root.bind("<B1-Motion>", self.drag_move)
        self.root.bind("<Escape>", lambda _event: self.close())

        self.results: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self.hotkey_ready = False
        self.kb = self.read_kb()
        self.build_ui()
        self.root.after(200, self.refresh_telemetry)
        self.root.after(100, self.poll_hotkey)
        self.root.after(100, self.poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self) -> None:
        header = Frame(self.root, bg="#101416")
        header.pack(fill=X, padx=12, pady=(10, 6))
        Label(header, text="GTA V  ·  AI TACTICAL COPILOT", fg="#a4c6a8", bg="#101416", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(header, text="×", command=self.close, fg="#d6dada", bg="#293033", bd=0, width=3).pack(side=RIGHT)

        self.telemetry = Label(self.root, text="正在读取遥测…", justify=LEFT, anchor="nw", fg="#f0f2ed", bg="#182022", font=("Consolas", 10), padx=10, pady=9, wraplength=390)
        self.telemetry.pack(fill=X, padx=10, pady=(0, 8))

        Button(self.root, text="AI 战术分析 (Alt+Q)", command=self.request_analysis, fg="#101416", bg="#a4c6a8", activebackground="#c0dfc4", bd=0, font=("Segoe UI", 10, "bold"), pady=7).pack(fill=X, padx=10, pady=(0, 8))
        Label(self.root, text="战术建议", fg="#dce6dd", bg="#101416", anchor="w", font=("Segoe UI", 9, "bold")).pack(fill=X, padx=12)
        self.advice = Text(self.root, wrap="word", bg="#182022", fg="#f0f2ed", insertbackground="#f0f2ed", relief="flat", padx=10, pady=8, font=("Segoe UI", 10))
        self.advice.pack(fill=BOTH, expand=True, padx=10, pady=(4, 8))
        self.advice.insert(END, "按 Alt+Q 截取当前画面并请求战术分析。\nEsc 关闭悬浮窗。")
        self.advice.configure(state="disabled")
        Label(self.root, text="拖动窗口可调整停靠位置", fg="#889495", bg="#101416", anchor="e", font=("Segoe UI", 8)).pack(fill=X, padx=12, pady=(0, 6))

    def drag_start(self, event: object) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def drag_move(self, event: object) -> None:
        self.root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    @staticmethod
    def read_kb() -> dict:
        try:
            return json.loads(KB_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"missions": {}}

    @staticmethod
    def read_telemetry() -> dict:
        try:
            return json.loads(TELEMETRY_PATH.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}

    def refresh_telemetry(self) -> None:
        data = self.read_telemetry()
        if data:
            loc = data.get("location") or {}
            status = data.get("player_status") or {}
            objectives = data.get("active_objectives") or []
            objective = next((o for o in objectives if o.get("role") == "Destination_Route"), objectives[0] if objectives else {})
            mission_id = data.get("active_mission_script", "未知")
            mission = self.kb.get("missions", {}).get(mission_id, {}).get("name", mission_id)
            distance = objective.get("distance_m")
            dist_text = f"{format_num(distance, 0)} 米" if distance is not None else "-- 米"
            role = objective.get("role", "无目标")
            text = (
                f"👤 {data.get('protagonist', '未知')}  |  ❤️ {status.get('hp', '?')}/{status.get('max_hp', '?')}  护甲 {status.get('armor', '?')}  |  ⭐ {status.get('wanted_level', '?')}\n"
                f"📍 {loc.get('zone_name', '?')} · {loc.get('street_name', '?')}\n"
                f"   ({format_num(loc.get('x'), 2)}, {format_num(loc.get('y'), 2)}, {format_num(loc.get('z'), 2)})\n"
                f"🎯 {mission} ({mission_id})\n🏁 距目标点: {dist_text} ({role})"
            )
        else:
            text = f"遥测文件尚不可用\n{TELEMETRY_PATH}"
        self.telemetry.configure(text=text)
        self.root.after(200, self.refresh_telemetry)

    def poll_hotkey(self) -> None:
        if os.name == "nt":
            if not self.hotkey_ready:
                self.hotkey_ready = bool(ctypes.windll.user32.RegisterHotKey(self.root.winfo_id(), HOTKEY_ID, MOD_ALT, VK_Q))
            msg = ctypes.wintypes.MSG()
            while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), self.root.winfo_id(), 0x0312, 0x0312, 1):
                if msg.wParam == HOTKEY_ID:
                    self.request_analysis()
        self.root.after(40, self.poll_hotkey)

    def request_analysis(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.set_advice("正在截取画面并分析…\n")
        threading.Thread(target=self.analyze_worker, daemon=True).start()

    def analyze_worker(self) -> None:
        try:
            if Image is None:
                raise RuntimeError("缺少 Pillow。请运行：py -m pip install Pillow")
            if mss is None:
                raise RuntimeError("缺少 mss。启动时会尝试自动安装；也可运行：py -m pip install mss")
            with mss.mss() as capture:
                shot = capture.grab(capture.monitors[0])
                image = Image.frombytes("RGB", shot.size, shot.rgb)
            image.thumbnail((1600, 900))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=78, optimize=True)
            screenshot = base64.b64encode(output.getvalue()).decode("ascii")
            telemetry = self.read_telemetry()
            mission_id = telemetry.get("active_mission_script", "")
            mission = self.kb.get("missions", {}).get(mission_id, {})
            api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("未配置 DEEPSEEK_API_KEY。请在 .env 中填写你自己的 API key 后重启悬浮窗。")
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
            context = json.dumps({"telemetry": telemetry, "mission_guide": mission}, ensure_ascii=False)
            prompt = "你是 GTA V 单机剧情任务实时战术助手。结合截图中的原生任务字幕、路况和战况，以及遥测和攻略数据库，简短回答：当前步骤判断、下一步具体行动、金牌条件提醒。不要臆测看不清的目标；标出不确定性。"
            payload = {
                "model": model,
                "stream": True,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt + "\n\n遥测与任务攻略：" + context},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + screenshot}}
                ]}]
            }
            request = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=90) as response:
                for raw in response:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        event = json.loads(chunk)
                        content = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if isinstance(content, str) and content:
                            self.results.put(("append", content))
                    except (json.JSONDecodeError, IndexError, AttributeError):
                        continue
            self.results.put(("done", ""))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:1000]
            except OSError:
                detail = str(exc)
            self.results.put(("error", f"DeepSeek API 返回 HTTP {exc.code}: {detail}"))
        except Exception as exc:
            self.results.put(("error", f"分析失败：{exc}"))

    def set_advice(self, value: str, append: bool = False) -> None:
        self.advice.configure(state="normal")
        if not append:
            self.advice.delete("1.0", END)
        self.advice.insert(END, value)
        self.advice.see(END)
        self.advice.configure(state="disabled")

    def poll_results(self) -> None:
        while True:
            try:
                kind, value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "append":
                self.set_advice(value, append=True)
            else:
                if kind == "error":
                    self.set_advice(value, append=True)
                self.busy = False
        self.root.after(100, self.poll_results)

    def close(self) -> None:
        if os.name == "nt" and self.hotkey_ready:
            ctypes.windll.user32.UnregisterHotKey(self.root.winfo_id(), HOTKEY_ID)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def install_mss_if_needed() -> None:
    global mss
    if mss is not None:
        return
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mss"], stdout=subprocess.DEVNULL)
        import mss as mss_module
        mss = mss_module
    except Exception:
        pass


if __name__ == "__main__":
    load_local_env()
    install_mss_if_needed()
    Overlay().run()
