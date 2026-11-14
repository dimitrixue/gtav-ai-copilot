from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import queue
import threading
import time
import urllib.error
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Button, Entry, Frame, Label, Text, Tk, Toplevel

if __package__:
    from .capture_and_telemetry import capture_screen_base64, read_telemetry, telemetry_path
    from .deepseek_client import stream_multimodal
else:
    from capture_and_telemetry import capture_screen_base64, read_telemetry, telemetry_path
    from deepseek_client import stream_multimodal

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import mss
except ImportError:
    mss = None


ROOT = Path(__file__).resolve().parent
KB_PATH = ROOT.parent / "data_kb" / "missions_kb.json"
ENV_PATH = ROOT.parent / ".env"
WINDOW_SUBCLASS_ID = 0x475441
HOTKEY_LABEL = "Num 1"
WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RI_KEY_BREAK = 0x0001
RI_KEY_EXTENDED = 0x0006
NUMPAD1_SCAN_CODE = 0x4F
NUMPAD2_SCAN_CODE = 0x50
NUMBER_ROW_2_SCAN_CODE = 0x03
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000


class RawInputDevice(ctypes.Structure):
    _fields_ = [
        ("usage_page", ctypes.wintypes.USHORT),
        ("usage", ctypes.wintypes.USHORT),
        ("flags", ctypes.wintypes.DWORD),
        ("window", ctypes.wintypes.HWND),
    ]


class RawInputHeader(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.wintypes.DWORD),
        ("size", ctypes.wintypes.DWORD),
        ("device", ctypes.wintypes.HANDLE),
        ("wparam", ctypes.wintypes.WPARAM),
    ]


class RawKeyboard(ctypes.Structure):
    _fields_ = [
        ("scan_code", ctypes.wintypes.USHORT),
        ("flags", ctypes.wintypes.USHORT),
        ("reserved", ctypes.wintypes.USHORT),
        ("virtual_key", ctypes.wintypes.USHORT),
        ("message", ctypes.wintypes.UINT),
        ("extra_information", ctypes.wintypes.ULONG),
    ]


class RawKeyboardInput(ctypes.Structure):
    _fields_ = [("header", RawInputHeader), ("keyboard", RawKeyboard)]


ANALYSIS_PROMPT = (
    "你是 GTA V Legacy 单机故事模式的中文任务助手。优先读截图底部的任务目标、左上角操作提示和小地图，"
    "用当前遥测里的任务、导航和目标标记交叉确认，再用攻略步骤定位进度。攻略是参考，不能假定玩家正处在第一步，"
    "也不要按任务编号猜下一关。自由活动时，如果地图上有明确可接的任务标记，指出一个看得到的标记；"
    "否则提示打开地图。过场、暂停或画面不清时，明确说明并给出一个能确认目标的操作。"
    "只给眼前一步，使用以下三行纯文本格式，避免剧透：\n"
    "当前任务：任务名和正在做的事；无法确认时直说。\n"
    "下一步：一个具体动作，带上可辨认的目标、位置或标记。\n"
    "按键：优先照抄游戏画面提示，注明按一下、长按或松开。"
    "只在操作明确且属于已知默认 PC 键位时给出键名，标为默认键位；不确定时写明该查哪个操作的键位。"
    "默认参考：Esc 打开暂停菜单，F 上下车，方向键上打开手机，长按左 Alt 打开角色轮盘，"
    "长按 Tab 打开武器轮盘，鼠标右键瞄准，左键射击，R 换弹。"
    "不要把 E 当成通用互动键。用户改过键位时以画面提示和游戏设置为准。"
)

QUESTION_PROMPT = (
    "你是「引路人」，GTA V Legacy 单机故事模式的中文助手。直接回答玩家的问题，简明具体，避免剧透。"
    "任务和位置参考提问时的遥测与攻略。没有足够信息时说明需要确认什么，不要猜测。"
)


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


def telemetry_age_seconds(data: dict) -> float | None:
    timestamp = data.get("timestamp")
    if isinstance(timestamp, int):
        return (time.time() * 1000 - timestamp) / 1000
    return None


def gta_foreground_window() -> int | None:
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    user32.GetWindowTextW.argtypes = (ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int)
    window = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(window, title, len(title))
    return window if title.value in {"Grand Theft Auto V", "Grand Theft Auto V Legacy"} else None


def local_guidance(data: dict, age_seconds: float | None) -> str:
    if not data or age_seconds is None or age_seconds >= 5:
        return f"下一步：回到故事模式，等待遥测更新。\n分析：{HOTKEY_LABEL} 可重新识别游戏画面。"

    objectives = data.get("active_objectives") or []
    if any(target.get("has_gps_route") is True for target in objectives):
        return "下一步：沿小地图导航线前往标记。\n按键：Esc → 地图，查看完整路线。"

    if data.get("is_mission_active"):
        if any(target.get("role") == "Destination_Route" for target in objectives):
            return f"下一步：前往任务的黄色标记。\n按键：到达后看画面提示，或按 {HOTKEY_LABEL} 分析。"
        return f"下一步：查看屏幕上的当前任务目标。\n分析：按 {HOTKEY_LABEL} 识别字幕和操作提示。"

    return "下一步：在地图上找可接的任务标记。\n按键：Esc → 地图。"


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

        self.results: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self._raw_keyboard_registered = False
        self._numpad_pressed = False
        self._question_keys_pressed: set[int] = set()
        self._window_handler = None
        self.question_window: Toplevel | None = None
        self.question_send: Button | None = None
        self.kb = self.read_kb()
        self.build_ui()
        self.root.after(200, self.refresh_telemetry)
        self.root.after_idle(self.configure_windows_overlay)
        self.root.after(100, self.poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self) -> None:
        header = Frame(self.root, bg="#101416")
        header.pack(fill=X, padx=12, pady=(10, 6))
        Label(header, text="GTA V  ·  AI TACTICAL COPILOT", fg="#a4c6a8", bg="#101416", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        Button(header, text="×", command=self.close, fg="#d6dada", bg="#293033", bd=0, width=3).pack(side=RIGHT)

        self.telemetry = Label(self.root, text="正在读取遥测…", justify=LEFT, anchor="nw", fg="#f0f2ed", bg="#182022", font=("Consolas", 10), padx=10, pady=9, wraplength=390)
        self.telemetry.pack(fill=X, padx=10, pady=(0, 8))

        self.next_step = Label(self.root, text="正在确认任务线索…", justify=LEFT, anchor="nw", fg="#dce6dd", bg="#222e27", font=("Segoe UI", 10), padx=10, pady=7, wraplength=390)
        self.next_step.pack(fill=X, padx=10, pady=(0, 8))
        Button(self.root, text=f"分析下一步和按键 ({HOTKEY_LABEL})", command=self.request_analysis, fg="#101416", bg="#a4c6a8", activebackground="#c0dfc4", bd=0, font=("Segoe UI", 10, "bold"), pady=7).pack(fill=X, padx=10, pady=(0, 8))
        Button(self.root, text="问引路人 (2)", command=self.open_question, fg="#dce6dd", bg="#293033", activebackground="#3a4649", bd=0, font=("Segoe UI", 10), pady=5).pack(fill=X, padx=10, pady=(0, 8))
        Label(self.root, text="引路人", fg="#dce6dd", bg="#101416", anchor="w", font=("Segoe UI", 9, "bold")).pack(fill=X, padx=12)
        self.advice = Text(self.root, wrap="word", bg="#182022", fg="#f0f2ed", insertbackground="#f0f2ed", relief="flat", padx=10, pady=8, font=("Segoe UI", 10))
        self.advice.pack(fill=BOTH, expand=True, padx=10, pady=(4, 8))
        self.advice.insert(END, f"按 {HOTKEY_LABEL} 分析游戏画面。\n按上排 2 或小键盘 2 打开文字提问。")
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

    def refresh_telemetry(self) -> None:
        data = read_telemetry()
        age_seconds = telemetry_age_seconds(data)
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
            if age_seconds is not None and age_seconds >= 5:
                text = f"遥测未更新（{age_seconds:.0f} 秒前）\n{text}"
        else:
            text = f"遥测文件尚不可用\n{telemetry_path()}"
        self.telemetry.configure(text=text)
        self.next_step.configure(text=local_guidance(data, age_seconds))
        self.root.after(200, self.refresh_telemetry)

    def configure_windows_overlay(self) -> None:
        if os.name != "nt":
            return

        hwnd = self.root.winfo_id()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = (ctypes.wintypes.HWND, ctypes.wintypes.UINT)
        user32.GetAncestor.restype = ctypes.wintypes.HWND
        user32.GetWindowLongW.argtypes = (ctypes.wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongW.argtypes = (ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.LONG)
        frame = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        style = user32.GetWindowLongW(frame, GWL_EXSTYLE)
        user32.SetWindowLongW(frame, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)

        controls = ctypes.windll.comctl32
        message_args = (ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        subclass_proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, *message_args, ctypes.c_size_t, ctypes.c_size_t)
        controls.DefSubclassProc.argtypes = message_args
        controls.DefSubclassProc.restype = ctypes.c_ssize_t
        controls.SetWindowSubclass.argtypes = (ctypes.wintypes.HWND, subclass_proc, ctypes.c_size_t, ctypes.c_size_t)
        controls.RemoveWindowSubclass.argtypes = (ctypes.wintypes.HWND, subclass_proc, ctypes.c_size_t)
        user32.RegisterRawInputDevices.argtypes = (ctypes.POINTER(RawInputDevice), ctypes.wintypes.UINT, ctypes.wintypes.UINT)
        user32.GetRawInputData.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.UINT, ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.wintypes.UINT), ctypes.wintypes.UINT)
        user32.GetRawInputData.restype = ctypes.wintypes.UINT

        @subclass_proc
        def handle_message(window, message, wparam, lparam, _subclass_id, _data):
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            if message == WM_INPUT:
                packet = RawKeyboardInput()
                size = ctypes.wintypes.UINT(ctypes.sizeof(packet))
                copied = user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(packet), ctypes.byref(size),
                                               ctypes.sizeof(RawInputHeader))
                if copied == ctypes.sizeof(packet) and packet.header.kind == 1:
                    self.handle_keyboard_input(packet.keyboard.scan_code, packet.keyboard.flags)
            return controls.DefSubclassProc(window, message, wparam, lparam)

        if not controls.SetWindowSubclass(frame, handle_message, WINDOW_SUBCLASS_ID, 0):
            self.set_advice("无法启用游戏内快捷键。可以点击面板按钮。")
            return
        self._window_handler = handle_message
        self._window_handle = frame
        keyboard = RawInputDevice(0x01, 0x06, RIDEV_INPUTSINK, frame)
        self._raw_keyboard_registered = bool(user32.RegisterRawInputDevices(ctypes.byref(keyboard), 1, ctypes.sizeof(keyboard)))
        if not self._raw_keyboard_registered:
            self.set_advice("无法注册游戏内快捷键。可以点击面板按钮。")

    def handle_keyboard_input(self, scan_code: int, flags: int) -> None:
        if flags & RI_KEY_EXTENDED:
            return
        if scan_code in (NUMBER_ROW_2_SCAN_CODE, NUMPAD2_SCAN_CODE):
            if flags & RI_KEY_BREAK:
                self._question_keys_pressed.discard(scan_code)
            elif scan_code not in self._question_keys_pressed and gta_foreground_window():
                self._question_keys_pressed.add(scan_code)
                self.results.put(("question", ""))
            return
        # The extended key with the same scan code is the separate End key.
        if scan_code != NUMPAD1_SCAN_CODE:
            return
        pressed = not (flags & RI_KEY_BREAK)
        if pressed and not self._numpad_pressed and gta_foreground_window():
            self.results.put(("analyze", ""))
        self._numpad_pressed = pressed

    def request_analysis(self) -> None:
        if self.busy or self.question_window is not None:
            return
        self.busy = True
        self.set_advice("正在识别任务目标和按键提示…\n")
        threading.Thread(target=self.request_worker, daemon=True).start()

    def open_question(self) -> None:
        if self.question_window is not None:
            self.question_window.lift()
            return

        context = self.tactical_context()
        game_window = gta_foreground_window() if os.name == "nt" else None
        window = Toplevel(self.root)
        self.question_window = window
        window.title("问引路人")
        window.configure(bg="#101416")
        window.attributes("-topmost", True)
        window.resizable(False, False)
        window.geometry(f"+{max(0, self.root.winfo_x())}+{max(0, self.root.winfo_y() + 110)}")

        def close_question(_event=None) -> str:
            if game_window and window.focus_displayof() is not None:
                user32 = ctypes.windll.user32
                user32.SetForegroundWindow.argtypes = (ctypes.wintypes.HWND,)
                user32.SetForegroundWindow(game_window)
            window.destroy()
            self.question_window = None
            self.question_send = None
            return "break"

        window.protocol("WM_DELETE_WINDOW", close_question)
        window.bind("<Escape>", close_question)

        Label(window, text="想问引路人什么？", fg="#f0f2ed", bg="#101416", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(10, 6))
        entry = Entry(window, width=34, font=("Segoe UI", 12))
        entry.pack(fill=X, padx=12, ipady=4)

        def ignore_shortcut_repeat(_event) -> str | None:
            if self._question_keys_pressed:
                return "break"
            return None

        for key in ("2", "KP_2", "KP_Down"):
            entry.bind(f"<KeyPress-{key}>", ignore_shortcut_repeat)

        def submit(_event=None) -> str:
            question = entry.get().strip()
            if question and not self.busy:
                close_question()
                self.busy = True
                self.set_advice(f"你：{question}\n\n引路人：")
                threading.Thread(target=self.request_worker, args=(question, context), daemon=True).start()
            return "break"

        controls = Frame(window, bg="#101416")
        controls.pack(fill=X, padx=12, pady=(8, 10))
        input_hint = "Win + 空格切换输入法\nEnter 发送 · Esc 取消" if os.name == "nt" else "Enter 发送 · Esc 取消"
        Label(controls, text=input_hint, justify=LEFT, fg="#a4b0b0", bg="#101416", font=("Segoe UI", 9)).pack(side=LEFT)
        self.question_send = Button(controls, command=submit, font=("Segoe UI", 10))
        self.question_send.pack(side=RIGHT)
        self.update_question_send()
        window.bind("<Return>", submit)
        window.bind("<KP_Enter>", submit)
        window.wait_visibility()
        if os.name == "nt":
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow.argtypes = (ctypes.wintypes.HWND,)
            frame = user32.GetAncestor(window.winfo_id(), GA_ROOT)
            if not user32.SetForegroundWindow(frame):
                entry.focus_set()
                return
        entry.focus_force()

    def update_question_send(self) -> None:
        if self.question_send is not None:
            self.question_send.configure(
                text="等待上一条回复…" if self.busy else "发送",
                state="disabled" if self.busy else "normal",
            )

    def tactical_context(self) -> dict:
        telemetry = read_telemetry()
        age_seconds = telemetry_age_seconds(telemetry)
        if age_seconds is None or age_seconds >= 5:
            telemetry = {}
        mission_id = telemetry.get("active_mission_script", "")
        mission = self.kb.get("missions", {}).get(mission_id, {})
        return {"telemetry": telemetry, "telemetry_current": bool(telemetry), "mission_guide": mission}

    @staticmethod
    def capture_screenshot() -> str:
        if Image is None:
            raise RuntimeError("缺少 Pillow。请运行：py -m pip install Pillow")
        if mss is None:
            raise RuntimeError("缺少 mss。启动时会尝试自动安装；也可运行：py -m pip install mss")
        return capture_screen_base64()

    def request_worker(self, question: str = "", context: dict | None = None) -> None:
        try:
            if context is None:
                context = self.tactical_context()
            if question:
                response = stream_multimodal(f"{QUESTION_PROMPT}\n\n玩家的问题：{question}", context)
            else:
                screenshot = self.capture_screenshot()
                response = stream_multimodal(ANALYSIS_PROMPT, context, screenshot)
            received_text = False
            for content in response:
                received_text = True
                self.results.put(("append", content))
            if not received_text:
                raise RuntimeError("模型未返回回复")
            self.results.put(("done", ""))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read(4096).decode("utf-8", "replace")
            except OSError:
                detail = str(exc)
            for name in ("PARATERA_API_KEY", "DEEPSEEK_API_KEY"):
                key = os.environ.get(name, "").strip()
                if key:
                    detail = detail.replace(key, "[已隐藏]")
            self.results.put(("error", f"模型 API 返回 HTTP {exc.code}: {detail[:1000]}"))
        except Exception as exc:
            action = "提问" if question else "分析"
            self.results.put(("error", f"{action}失败：{exc}"))

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
            if kind == "analyze":
                if gta_foreground_window():
                    self.request_analysis()
            elif kind == "question":
                if gta_foreground_window():
                    self.open_question()
            elif kind == "append":
                self.set_advice(value, append=True)
            else:
                if kind == "error":
                    self.set_advice(value, append=True)
                self.busy = False
                self.update_question_send()
        self.root.after(100, self.poll_results)

    def close(self) -> None:
        if self._raw_keyboard_registered:
            keyboard = RawInputDevice(0x01, 0x06, RIDEV_REMOVE, None)
            ctypes.windll.user32.RegisterRawInputDevices(ctypes.byref(keyboard), 1, ctypes.sizeof(keyboard))
        if self._window_handler is not None:
            ctypes.windll.comctl32.RemoveWindowSubclass(self._window_handle, self._window_handler, WINDOW_SUBCLASS_ID)
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
