# apps/windows-room/host_main.py
from __future__ import annotations

from pathlib import Path
import os
import sys


def _app_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


HERE = _app_dir()
# When frozen, BridgeApi modules are collected into _MEIPASS; when not, use sibling trees.
CC = HERE.parent / "windows-cc" if not getattr(sys, "frozen", False) else HERE
PANEL = HERE.parent / "windows-panel" if not getattr(sys, "frozen", False) else HERE
WIN = HERE.parents[1] / "scripts" / "win" if not getattr(sys, "frozen", False) else HERE
for p in (HERE, CC, PANEL, WIN):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bridge_api import BridgeApi  # noqa: E402
import panel_api  # noqa: E402


def discover_root() -> Path:
    env = os.environ.get("JARVIS_HOME") or os.environ.get("JARVIS_ROOT")
    if env:
        p = Path(env)
        if panel_api.is_valid_root(p):
            return p.resolve()
    # Prefer install root next to exe when frozen
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else HERE
    found = panel_api.discover_root(exe_dir=exe_dir, default=Path(r"C:\Users\rajk1\jarvis"))
    if found:
        return found
    box = Path("/home/box/jarvis")
    if panel_api.is_valid_root(box):
        return box.resolve()
    raise SystemExit("JARVIS_ROOT not found (need STATE.md + POLICY.yaml)")


def main():
    import webview

    root = discover_root()
    os.environ.setdefault("JARVIS_HOME", str(root))
    try:
        from llm_providers import load_secrets

        load_secrets(root)
    except Exception:
        pass
    api = BridgeApi(root=root)
    try:
        import voice

        voice.load_prefs(root)
    except Exception:
        pass
    ui = str(HERE / "ui" / "index.html")
    webview.create_window(
        "JARVIS Room",
        url=ui,
        js_api=api,
        width=1440,
        height=900,
    )
    webview.start(http_server=True, debug=False)


if __name__ == "__main__":
    main()
