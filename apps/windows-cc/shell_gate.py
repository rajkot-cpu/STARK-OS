# apps/windows-cc/shell_gate.py
"""Allowlist for agent shell commands. Anything not matched needs R3 confirmation."""
from __future__ import annotations

import re

_META = ("|", ";", "&", "`", "$", "%", ">", "<", "\n", "\r")


def normalize(cmd: str) -> str:
    return " ".join((cmd or "").strip().split())


def _is_relative_safe(arg: str) -> bool:
    if ".." in arg:
        return False
    if arg.startswith(("/", "\\", "~")):
        return False
    if re.match(r"^[A-Za-z]:", arg):
        return False
    return True


def is_allowlisted(cmd: str) -> bool:
    c = normalize(cmd)
    if not c or any(m in c for m in _META):
        return False
    low = c.lower()
    if low == "git status":
        return True
    if re.fullmatch(r"git log -n ([1-9]|1[0-9]|20)( --oneline)?", low):
        return True
    if low == "python -m unittest" or low.startswith("python -m unittest "):
        rest = c[len("python -m unittest"):].strip()
        if not rest:
            return True
        return all(_is_relative_safe(a) for a in rest.split())
    head, _, rest = c.partition(" ")
    if head.lower() in ("dir", "ls"):
        return all(_is_relative_safe(a) for a in rest.split())
    return False
