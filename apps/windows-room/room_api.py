# apps/windows-room/room_api.py
"""Room host helper. The bridge is apps/windows-cc BridgeApi — not a second copy."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Methods the workshop UI calls. All of them live on windows-cc BridgeApi.
REQUIRED_METHODS = (
    "status",
    "metrics",
    "feed",
    "memory",
    "llms",
    "agents",
    "agent_start",
    "agent_stop",
    "voice_turn",
    "chat",
    "speak",
    "listen",
    "mute",
    "session_start",
    "dry_run_workday",
    "start_workday",
    "skills",
    "brief",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cc_bridge_path() -> Path:
    return (_repo_root() / "apps" / "windows-cc" / "bridge_api.py").resolve()


def ensure_paths() -> None:
    """Put windows-cc first so `import bridge_api` is the Command Center module."""
    here = Path(__file__).resolve().parent
    root = _repo_root()
    # insert(0) — last entry ends up at the front.
    for p in (
        here,
        here.parent / "windows-panel",
        root / "scripts" / "win",
        here.parent / "windows-cc",
    ):
        s = str(p)
        if s in sys.path:
            sys.path.remove(s)
        sys.path.insert(0, s)


def load_bridge_class():
    ensure_paths()
    expected = _cc_bridge_path()
    existing = sys.modules.get("bridge_api")
    if existing is not None and not getattr(sys, "frozen", False):
        actual = Path(getattr(existing, "__file__", "")).resolve()
        if actual != expected:
            del sys.modules["bridge_api"]
    import bridge_api  # windows-cc when running from source

    if not getattr(sys, "frozen", False):
        actual = Path(bridge_api.__file__).resolve()
        if actual != expected:
            raise ImportError(f"expected windows-cc bridge at {expected}, got {actual}")
    return bridge_api.BridgeApi


def discover_root() -> Path:
    ensure_paths()
    import panel_api

    env = os.environ.get("JARVIS_HOME") or os.environ.get("JARVIS_ROOT")
    if env:
        p = Path(env)
        if panel_api.is_valid_root(p):
            return p.resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
    else:
        exe_dir = Path(__file__).resolve().parent
    found = panel_api.discover_root(
        exe_dir=exe_dir,
        default=Path(r"C:\Users\rajk1\jarvis"),
    )
    if found:
        return found
    for cand in (Path("/home/box/jarvis"), _repo_root()):
        if panel_api.is_valid_root(cand):
            return cand.resolve()
    raise SystemExit("JARVIS_ROOT not found (need STATE.md + POLICY.yaml)")


def make_api(root: Path | None = None):
    """Construct the Command Center bridge. Does not invent status or metrics."""
    BridgeApi = load_bridge_class()
    if root is None:
        root = discover_root()
    root = Path(root)
    os.environ.setdefault("JARVIS_HOME", str(root))
    try:
        from llm_providers import load_secrets

        load_secrets(root)
    except Exception:
        pass
    api = BridgeApi(root=root)
    missing = [name for name in REQUIRED_METHODS if not callable(getattr(api, name, None))]
    if missing:
        raise RuntimeError("BridgeApi missing methods: " + ", ".join(missing))
    try:
        import voice

        voice.load_prefs(root)
    except Exception:
        pass
    return api
