# apps/windows-cc/secrets_store.py
"""API keys in Windows Credential Manager — Master Upgrade Module 1C.

Lookup order used by llm_providers.load_secrets():
  1. process environment
  2. Windows Credential Manager, generic credentials named "JARVIS/<KEY_NAME>"
  3. secrets/api_keys.env (fallback; kept for machines without Credential Manager)

`migrate(root)` copies every KEY=VALUE from api_keys.env into Credential Manager, reads each
one back to verify it, and only when *all* verify does it rewrite api_keys.env with the values
removed (names kept as comments, so the file documents what is stored where). If any key fails,
nothing in the file is changed. Values are never printed or logged; only key names and counts.

CLI:  python secrets_store.py status|migrate [JARVIS_ROOT]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PREFIX = "JARVIS/"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
MIGRATED_MARK = "# stored in Windows Credential Manager as "


def available() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes  # noqa: F401

        return True
    except Exception:
        return False


def _api():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    return ctypes, CREDENTIAL, adv


def write(name: str, value: str) -> bool:
    if not available() or not name or not value:
        return False
    ctypes, CREDENTIAL, adv = _api()
    blob = value.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = PREFIX + name
    c.Comment = "JARVIS API key"
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    c.UserName = "jarvis"
    return bool(adv.CredWriteW(ctypes.byref(c), 0))


def read(name: str) -> str:
    if not available() or not name:
        return ""
    ctypes, CREDENTIAL, adv = _api()
    p = ctypes.POINTER(CREDENTIAL)()
    if not adv.CredReadW(PREFIX + name, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return ""
    try:
        n = p.contents.CredentialBlobSize
        raw = ctypes.string_at(p.contents.CredentialBlob, n)
        return raw.decode("utf-16-le")
    except Exception:
        return ""
    finally:
        adv.CredFree(p)


def delete(name: str) -> bool:
    if not available():
        return False
    _, _, adv = _api()
    return bool(adv.CredDeleteW(PREFIX + name, CRED_TYPE_GENERIC, 0))


def env_path(root: Path | str) -> Path:
    return Path(root) / "secrets" / "api_keys.env"


def parse_env(path: Path) -> list[tuple[str, str]]:
    out = []
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v:
            out.append((k, v))
    return out


def migrated_names(root: Path | str) -> list[str]:
    """Key names api_keys.env says live in Credential Manager."""
    p = env_path(root)
    if not p.is_file():
        return []
    names = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        if raw.startswith(MIGRATED_MARK):
            n = raw[len(MIGRATED_MARK):].strip()
            if n.startswith(PREFIX):
                names.append(n[len(PREFIX):])
    return names


def load_into_env(root: Path | str, names: list[str] | None = None) -> int:
    """Copy Credential Manager keys into os.environ (no overwrite). Returns count set."""
    if not available():
        return 0
    n = 0
    for name in names if names is not None else migrated_names(root):
        if os.environ.get(name, "").strip():
            continue
        v = read(name)
        if v:
            os.environ[name] = v
            n += 1
    return n


def status(root: Path | str) -> dict:
    p = env_path(root)
    in_file = [k for k, _ in parse_env(p)]
    migrated = migrated_names(root)
    in_store = [n for n in migrated if available() and read(n)]
    return {"credential_manager": available(), "file": str(p), "file_exists": p.is_file(),
            "plaintext_keys_in_file": in_file, "keys_in_credential_manager": in_store,
            "missing_from_store": [n for n in migrated if n not in in_store]}


def migrate(root: Path | str) -> dict:
    if not available():
        return {"ok": False, "error": "Windows Credential Manager not available; api_keys.env left unchanged"}
    p = env_path(root)
    pairs = parse_env(p)
    if not pairs:
        return {"ok": True, "data": {"migrated": [], "note": "no plaintext keys in api_keys.env"}}
    failed = []
    for k, v in pairs:
        if not write(k, v) or read(k) != v:
            failed.append(k)
    if failed:
        return {"ok": False, "error": "verification failed; api_keys.env left unchanged",
                "failed": failed}
    names = {k for k, _ in pairs}
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() in names:
            k = s.split("=", 1)[0].strip()
            lines.append(f"{MIGRATED_MARK}{PREFIX}{k}")
            continue
        lines.append(raw)
    lines.insert(0, f"# {stamp}: keys moved to Windows Credential Manager (verified). "
                    "Add a KEY=VALUE line here only as a fallback.")
    tmp = p.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    try:
        from cc_settings import audit

        audit(root, "safety", "secrets_migrated", f"{len(names)} keys to Credential Manager: {sorted(names)}")
    except Exception:
        pass
    return {"ok": True, "data": {"migrated": sorted(names)}}


if __name__ == "__main__":
    import json

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(os.environ.get("JARVIS_HOME") or ".")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    r = migrate(root) if cmd == "migrate" else status(root)
    print(json.dumps(r, indent=2))
