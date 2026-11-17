# apps/windows-cc/host_main.py
from __future__ import annotations

from pathlib import Path
import os
import threading
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


def _install_crash_log(root: Path) -> None:
    """Uncaught exceptions (main + worker threads) go to logs/ui-errors.log; the exe is --windowed."""
    import threading
    import traceback

    from bridge_api import log_error

    def _hook(tp, val, tb):
        log_error(root, "python.uncaught", "".join(traceback.format_exception(tp, val, tb)))

    sys.excepthook = _hook
    threading.excepthook = lambda a: log_error(
        root, f"thread.{getattr(a.thread, 'name', '?')}",
        "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def main():
    root = discover_root()
    os.environ.setdefault("JARVIS_HOME", str(root))
    try:
        from llm_providers import load_secrets

        load_secrets(root)
    except Exception:
        pass
    _install_crash_log(root)
    from bridge_api import log_error as _log
    import session_log

    session_log.enable_faulthandler(root)
    sess = session_log.SessionLog(root, log=_log)
    sess.start()  # reports a previous session that ended without a clean exit
    sess.start_heartbeat(30.0)
    exit_reason = "webview loop ended"
    api = BridgeApi(root=root)
    try:
        api.start_safety()  # Emergency STOP: STOP-file watcher + Ctrl+Alt+Shift+S
    except Exception:
        pass
    try:
        api.start_local_api()  # Phase 3: 127.0.0.1-only HTTP API (token in Credential Manager)
    except Exception:
        pass
    try:
        threading.Thread(target=api.memory_reindex, daemon=True, name="memory-reindex").start()
    except Exception:
        pass
    try:
        import voice

        voice.load_prefs(root)
    except Exception:
        pass
    ui = str(HERE / "ui" / "index.html")
    win = webview.create_window(
        "JARVIS Command Center",
        url=ui,
        js_api=api,
        width=1440,
        height=900,
    )
    # Diagnostics: a window closed by the user/OS logs "window closing"; a crash leaves no such line.
    try:
        from bridge_api import log_error

        def _closing(*a):
            nonlocal exit_reason
            exit_reason = "window closed (by user or Windows)"
            log_error(root, "host", "window closing (closed by user or Windows)", "info")

        win.events.closing += _closing
    except Exception:
        pass
    try:
        api.autostart()  # wake word only if the operator enabled it earlier
    except Exception:
        pass
    try:
        # JARVIS_WEBVIEW_DEBUG=1 enables WebView2 DevTools (diagnostics only; off by default).
        webview.start(http_server=True, debug=os.environ.get("JARVIS_WEBVIEW_DEBUG") == "1")
    except BaseException as e:
        exit_reason = f"webview error: {type(e).__name__}: {e}"
        raise
    finally:
        try:
            sess.end(exit_reason)
        except Exception:
            pass
        try:
            from bridge_api import log_error

            log_error(root, "host", "Jarvis exiting (webview loop ended)", "info")
        except Exception:
            pass
        api.shutdown()


if __name__ == "__main__":
    main()
