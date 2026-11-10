# apps/windows-cc/readiness.py
"""Jarvis readiness score — weighted checks, never returns secret values."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

# Weights must sum to 100.
CHECKS: tuple[dict[str, Any], ...] = (
    {
        "id": "llm_any_key",
        "label": "At least one AI key is set",
        "weight": 15,
        "fix": "Add an AI key (OpenAI, Gemini, Anthropic, or Groq) on the API Keys page",
    },
    {
        "id": "gemini_key",
        "label": "Gemini key set (agents primary)",
        "weight": 12,
        "fix": "Add a Gemini key on the API Keys page",
    },
    {
        "id": "openai_key",
        "label": "OpenAI key set (chat fallback)",
        "weight": 10,
        "fix": "Add an OpenAI key on the API Keys page",
    },
    {
        "id": "llm_reachable",
        "label": "An AI provider is reachable",
        "weight": 12,
        "fix": "Check your AI keys — Jarvis could not reach a provider",
    },
    {
        "id": "stt",
        "label": "Voice listening (STT) available",
        "weight": 8,
        "fix": "Install PyAudio so Jarvis can hear the microphone",
    },
    {
        "id": "tts",
        "label": "Voice speech (TTS) available",
        "weight": 6,
        "fix": "Install a speech engine (pyttsx3) so Jarvis can talk",
    },
    {
        "id": "policy_ok",
        "label": "POLICY.yaml loads and is approved",
        "weight": 10,
        "fix": "Approve POLICY.yaml (status must be approved)",
    },
    {
        "id": "policy_paths",
        "label": "Protected folders are real paths",
        "weight": 8,
        "fix": "Replace placeholder paths in POLICY.yaml with your real protected folders",
    },
    {
        "id": "agents",
        "label": "Agents registry loads",
        "weight": 7,
        "fix": "Repair the agents registry — roles failed to load",
    },
    {
        "id": "audit_log",
        "label": "Audit log is writable",
        "weight": 6,
        "fix": "Create a writable logs folder so Jarvis can write the audit log",
    },
    {
        "id": "secrets_file",
        "label": "Secrets file exists",
        "weight": 6,
        "fix": "Create secrets/api_keys.env (copy from the example template)",
    },
)

_LLM_KEYS = (
    ("JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",)),
    ("JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    ("JARVIS_ANTHROPIC_API_KEY", ("ANTHROPIC_API_KEY",)),
    ("JARVIS_GROQ_API_KEY", ("GROQ_API_KEY",)),
)


def _secrets_map(root: Path) -> dict[str, str]:
    path = Path(root) / "secrets" / "api_keys.env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                out[key] = val
    except Exception:
        return out
    return out


def _present(names: tuple[str, ...], env: Mapping[str, str], secrets: Mapping[str, str]) -> bool:
    for name in names:
        if str(env.get(name, "")).strip() or str(secrets.get(name, "")).strip():
            return True
    return False


def _any_llm_key(env: Mapping[str, str], secrets: Mapping[str, str]) -> bool:
    for primary, aliases in _LLM_KEYS:
        if _present((primary, *aliases), env, secrets):
            return True
    if _present(("JARVIS_OLLAMA_BASE",), env, secrets):
        return True
    return False


def _parse_policy(root: Path) -> dict:
    path = Path(root) / "POLICY.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _paths_real(paths: list) -> bool:
    if not paths:
        return False
    for raw in paths:
        text = str(raw).strip()
        if not text or "PLACEHOLDER" in text.upper():
            return False
    return True


def _stt_available() -> bool:
    try:
        import pyaudio  # noqa: F401
    except Exception:
        return False
    try:
        import speech_recognition  # noqa: F401
    except Exception:
        return False
    return True


def _tts_available() -> bool:
    try:
        import pyttsx3  # noqa: F401

        return True
    except Exception:
        pass
    try:
        import win32com.client  # noqa: F401

        return True
    except Exception:
        pass
    # Windows SAPI via PowerShell is the last TTS fallback in voice.py.
    return sys.platform.startswith("win")


def _agents_available() -> bool:
    try:
        from agents.registry import ROLES

        return isinstance(ROLES, list) and len(ROLES) >= 1
    except Exception:
        return False


def _audit_writable(root: Path) -> bool:
    logs = Path(root) / "logs"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        path = logs / "audit.jsonl"
        with path.open("a", encoding="utf-8"):
            pass
        return True
    except Exception:
        return False


def _cached_probes() -> list[dict] | None:
    try:
        from llm_providers import cached_probes

        return cached_probes()
    except Exception:
        return None


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def compute_extras(root: Path) -> list[dict]:
    """Optional features: info only, never part of the score (opt-ins may be off)."""
    out = []

    def add(cid, label, ok, note):
        out.append({"id": cid, "label": label, "ok": bool(ok), "note": note, "weight": 0, "info": True})

    try:
        from cc_settings import load

        s = load(root)
    except Exception:
        s = {"wake_word": False, "whisper_model": "tiny.en"}
    try:
        from stt import whisper_installed, whisper_model_ready

        model_ok = whisper_installed() and whisper_model_ready(root, s.get("whisper_model", "tiny.en"))
    except Exception:
        model_ok = False
    add("offline_stt", "Offline speech model downloaded", model_ok,
        "Settings > Download offline model (or it downloads on first Tap to Speak)")
    add("wake_word", "Hey Jarvis wake word on", s.get("wake_word"),
        "Optional: Settings > Always listen for Hey Jarvis")
    add("neural_voice", "Natural voice (edge-tts) installed", _importable("edge_tts"),
        "Falls back to the Windows voice when offline")
    add("web_search", "Agent web search installed", _importable("ddgs"), "Research/Browser agents")
    try:
        from mcp_client import load_servers

        n = len([x for x in load_servers(root)[0] if x["enabled"]])
    except Exception:
        n = 0
    add("mcp_servers", f"MCP tool servers enabled: {n}", n > 0,
        "Optional: add servers to config/mcp_servers.json")
    return out


def compute_readiness(
    root: Path | str,
    *,
    env: Mapping[str, str] | None = None,
    probes: list[dict] | None = None,
    stt_ok: bool | None = None,
    tts_ok: bool | None = None,
    agents_ok: bool | None = None,
) -> dict:
    """Return {score_pct: int, checks: [...]} with booleans only — never secret values."""
    root = Path(root)
    environ: Mapping[str, str] = os.environ if env is None else env
    secrets = _secrets_map(root)
    policy = _parse_policy(root)

    any_key = _any_llm_key(environ, secrets)
    gemini = _present(("JARVIS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"), environ, secrets)
    openai = _present(("JARVIS_OPENAI_API_KEY", "OPENAI_API_KEY"), environ, secrets)

    rows = probes if probes is not None else _cached_probes()
    if rows:
        reachable = any(str(r.get("state") or "") == "connected" for r in rows)
    else:
        reachable = any_key

    flags = {
        "llm_any_key": any_key,
        "gemini_key": gemini,
        "openai_key": openai,
        "llm_reachable": reachable,
        "stt": _stt_available() if stt_ok is None else bool(stt_ok),
        "tts": _tts_available() if tts_ok is None else bool(tts_ok),
        "policy_ok": policy.get("status") == "approved",
        "policy_paths": _paths_real(policy.get("restricted") or []),
        "agents": _agents_available() if agents_ok is None else bool(agents_ok),
        "audit_log": _audit_writable(root),
        "secrets_file": (root / "secrets" / "api_keys.env").is_file(),
    }

    checks = []
    score = 0
    for spec in CHECKS:
        ok = bool(flags[spec["id"]])
        if ok:
            score += int(spec["weight"])
        checks.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "ok": ok,
                "weight": int(spec["weight"]),
                "fix": spec["fix"],
            }
        )
    try:
        extras = compute_extras(root)
    except Exception:
        extras = []
    return {"score_pct": int(score), "checks": checks, "extras": extras}
