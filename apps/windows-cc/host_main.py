# apps/windows-cc/host_main.py
from __future__ import annotations

from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "windows-panel"))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "win"))

import webview  # noqa: E402
from bridge_api import BridgeApi  # noqa: E402
import panel_api  # noqa: E402


def discover_root() -> Path:
    env = os.environ.get("JARVIS_HOME") or os.environ.get("JARVIS_ROOT")
    if env:
        p = Path(env)
        if panel_api.is_valid_root(p):
            return p.resolve()
    found = panel_api.discover_root(exe_dir=HERE, default=Path(r"C:\Users\rajk1\jarvis"))
    if found:
        return found
    # box fallback for local smoke
    box = Path("/home/box/jarvis")
    if panel_api.is_valid_root(box):
        return box.resolve()
    raise SystemExit("JARVIS_ROOT not found (need STATE.md + POLICY.yaml)")


def main():
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
        "JARVIS Command Center",
        url=ui,
        js_api=api,
        width=1440,
        height=900,
    )
    webview.start(http_server=True, debug=False)


if __name__ == "__main__":
    main()
