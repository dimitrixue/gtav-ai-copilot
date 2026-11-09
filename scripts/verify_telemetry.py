import json
import os
import sys
import time
import tempfile
from pathlib import Path


GAME_ROOT = Path(os.environ.get("GTAV_GAME_PATH", r"D:\steam\steamapps\common\Grand Theft Auto V"))
REQUIRED_FILES = (
    "ScriptHookV.dll",
    "dinput8.dll",
    "ScriptHookVDotNet.dll",
    "ScriptHookVDotNet2.dll",
    "ScriptHookVDotNet3.dll",
    "Rampage.asi",
)


def verify_telemetry_stream() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    loader = "ScriptHookVDotNet-Loader.asi"
    if not (GAME_ROOT / loader).is_file() and (GAME_ROOT / "ScriptHookVDotNet.asi").is_file():
        loader = "ScriptHookVDotNet.asi"
    script = Path("scripts", "GTAVTelemetryServer.dll")
    if not (GAME_ROOT / script).is_file():
        script = script.with_suffix(".cs")
    required = (*REQUIRED_FILES, loader, script)
    missing = [name for name in required if not (GAME_ROOT / name).is_file()]
    for name in required:
        state = "OK" if name not in missing else "MISSING"
        print(f"[{state}] {GAME_ROOT / name}")

    log_path = GAME_ROOT / "ScriptHookVDotNet.log"
    compile_ok = False
    if log_path.exists():
        log = log_path.read_text(encoding="utf-8", errors="replace")
        lines = log.rsplit("[DEBUG] Loading scripts from ", 1)[-1].splitlines()
        matches = [line for line in lines if script.name in line]
        print(f"[LOG] {log_path}")
        print("\n".join(matches[-10:]) if matches else "[!] No telemetry script entry found in log.")
        compile_errors = [
            line for line in lines
            if "[ERROR]" in line and script.name in line
        ]
        compile_ok = bool(matches) and not compile_errors
        if compile_errors:
            print("[!] Compilation errors detected:")
            print("\n".join(compile_errors[-10:]))
    else:
        print(f"[!] ScriptHookVDotNet.log not found: {log_path}")

    telemetry_path = Path(tempfile.gettempdir()) / "gtav_ai_telemetry.json"
    if not telemetry_path.exists():
        print(f"[!] Telemetry file not found: {telemetry_path}. Launch Story Mode first.")
        return 1

    try:
        data = json.loads(telemetry_path.read_text(encoding="utf-8-sig"))
        age_ms = int(time.time() * 1000) - int(data.get("timestamp", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"[!] Telemetry is unreadable: {exc}")
        return 1

    print(f"[TELEMETRY] age={age_ms} ms")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if not missing and compile_ok and 0 <= age_ms < 5000 else 1


if __name__ == "__main__":
    raise SystemExit(verify_telemetry_stream())
