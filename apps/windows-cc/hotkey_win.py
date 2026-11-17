# apps/windows-cc/hotkey_win.py
"""Global Emergency STOP hotkey (Ctrl+Alt+Shift+S) via Win32 RegisterHotKey.

Works while Jarvis is minimised or another app has focus. No keyboard hook, no extra
dependency: a dedicated thread owns the hotkey and runs a GetMessage loop.
"""
from __future__ import annotations

import os
import threading
from typing import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x4A53  # "JS"
DEFAULT_MODS = MOD_CONTROL | MOD_ALT | MOD_SHIFT
DEFAULT_VK = ord("S")
LABEL = "Ctrl+Alt+Shift+S"


def parse(spec: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+Shift+S' -> (mods, vk). Letters/digits and F1-F12 only."""
    mods, vk = 0, None
    for part in [p.strip().lower() for p in str(spec or "").split("+") if p.strip()]:
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 12:
            vk = 0x70 + int(part[1:]) - 1
        else:
            return None
    if vk is None or mods == 0:
        return None
    return mods, vk


class GlobalHotkey:
    def __init__(self, on_press: Callable[[], object], spec: str = LABEL):
        self.on_press = on_press
        self.spec = spec
        self.state = "off"   # off | active | failed | unsupported
        self.error = ""
        self._thread: threading.Thread | None = None
        self._tid = 0

    def start(self) -> str:
        if os.name != "nt":
            self.state = "unsupported"
            return self.state
        parsed = parse(self.spec)
        if not parsed:
            self.state, self.error = "failed", f"bad hotkey {self.spec!r}"
            return self.state
        ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(parsed, ready), name="stop-hotkey", daemon=True)
        self._thread.start()
        ready.wait(3.0)
        return self.state

    def _loop(self, parsed, ready: threading.Event) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()
        mods, vk = parsed
        if not user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            self.state = "failed"
            self.error = f"RegisterHotKey failed (error {kernel32.GetLastError()}); another app may own {self.spec}"
            ready.set()
            return
        self.state = "active"
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self.on_press()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self.state = "off"

    def stop(self) -> None:
        if os.name == "nt" and self._tid:
            try:
                import ctypes

                ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass
