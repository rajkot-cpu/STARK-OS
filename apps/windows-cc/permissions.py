# apps/windows-cc/permissions.py
"""Master Upgrade permission Levels 1-4 mapped onto Jarvis's existing R1-R4 tiers.

This is a description + lookup layer only. It never lowers an existing tier: every action keeps
the tier the code already enforces (R3 = confirm each time, R4 = typed CONFIRM). Anything not
listed is treated as Level 4 / R4 (most restrictive) by `level_for()`.
"""
from __future__ import annotations

LEVELS = {
    1: {"name": "Read only", "tier": "R1", "rule": "Runs automatically and is logged.",
        "doc_examples": ["read files", "research", "analyse data", "generate reports"]},
    2: {"name": "Routine automation", "tier": "R2", "rule": "Runs automatically, reversible, logged.",
        "doc_examples": ["organise approved folders", "prepare documents", "run approved scripts"]},
    3: {"name": "Controlled external actions", "tier": "R3",
        "rule": "Needs your confirmation every time.",
        "doc_examples": ["send email", "publish", "create accounts", "contact customers", "deploy",
                         "change external services"]},
    4: {"name": "High-risk actions", "tier": "R4",
        "rule": "Needs typed confirmation every time; live trading also needs separate approval.",
        "doc_examples": ["spend money", "move funds", "place live trades", "sign agreements",
                         "delete important data", "change security settings", "share sensitive info"]},
}

# Existing Jarvis actions and the tier the code enforces today.
ACTIONS = {
    "list_dir": 1, "read_file": 1, "code_search": 1, "web_search": 1, "web_fetch": 1,
    "chat": 1, "readiness": 1, "metrics": 1,
    "memory_note": 2, "write_file_new": 2, "make_dir": 2, "shell_allowlisted": 2,
    "video_render_local": 2, "settings_change": 2,
    "shell_other": 3, "run_code": 3, "overwrite_file": 3, "delete_file": 3, "mcp_tool": 3,
    "screen_read": 3, "wake_word_enable": 3, "start_workday": 3,
    "publish_upload": 4, "send_message": 4, "purchase": 4, "live_trade": 4, "move_funds": 4,
    "change_security": 4,
}

NOT_ENABLED = ("publish_upload", "send_message", "purchase", "live_trade", "move_funds")


def level_for(action: str) -> int:
    return int(ACTIONS.get(str(action), 4))


def tier_for(action: str) -> str:
    return LEVELS[level_for(action)]["tier"]


def table() -> list[dict]:
    out = []
    for lvl, info in LEVELS.items():
        acts = sorted(a for a, l in ACTIONS.items() if l == lvl)
        out.append({"level": lvl, "name": info["name"], "tier": info["tier"], "rule": info["rule"],
                    "actions": acts, "not_enabled": [a for a in acts if a in NOT_ENABLED]})
    return out
