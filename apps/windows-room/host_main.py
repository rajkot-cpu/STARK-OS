# apps/windows-room/host_main.py
"""pywebview host for the workshop room. JS API is windows-cc BridgeApi."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from room_api import make_api  # noqa: E402


def main() -> int:
    api = make_api()
    # Relative ui/ URL + http_server so WebView2 allows ES module imports.
    # Frozen onefile extracts ui/ next to this file under _MEIPASS.
    os.chdir(HERE)
    import webview

    webview.create_window(
        "JARVIS Room // WORKSHOP",
        url="ui/index.html",
        js_api=api,
        width=1440,
        height=900,
        background_color="#04070b",
    )
    webview.start(http_server=True, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
