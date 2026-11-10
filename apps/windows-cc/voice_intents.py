"""Route a typed or spoken command to an agent, a reserved intent, or chat.

match(text) -> {"intent": "agent", "role", "goal", "verb"}
             | {"intent": "stop_agent", "role"}
             | {"intent": "start_trading"} | {"intent": "stop_trading"}   (reserved, not implemented here)
             | {"intent": "chat", "text"}
"""
from __future__ import annotations

import re

RESERVED = ("start_trading", "stop_trading")

ROLE_NAMES = {
    "builder": "builder", "build": "builder", "coding": "coding", "coder": "coding", "code": "coding",
    "research": "research", "researcher": "research", "memory": "memory", "browser": "browser",
    "task": "task", "tasks": "task", "system": "system",
}

_WAKE = re.compile(r"^\s*(?:(?:hey|hi|ok|okay|yo)\s+)?jarvis\b[\s,.:!-]*", re.I)
_POLITE = re.compile(r"^(?:please|can you|could you|would you|i want you to|i need you to|go ahead and|kindly)\s+", re.I)

_BUILD = re.compile(
    r"^(?:build|make|create|code|develop|generate|scaffold|set ?up|write)\b"
    r"(?!\s+(?:sure|it|me\s+(?:laugh|happy|smile)|(?:a|an)\s+(?:reminder|appointment|meeting|call|note|payment|order|trade)\b))"
    r"(?:\s+(?:me|us))?\s+(?:a|an|the|my|some|\w+)", re.I)
_NOTE = re.compile(r"^(?:remember|note that|make a note|take a note|write a note|save a note|note down)\b", re.I)
_RESEARCH = re.compile(
    r"^(?:research|find out|look up|lookup|search for|search|investigate|compare|find information|"
    r"find me information|dig into|study)\b", re.I)
_BROWSE = re.compile(r"^(?:browse|open (?:the )?(?:website|site|page|url)|go to (?:the )?(?:website|site)|"
                     r"visit|fetch (?:the )?(?:page|url|website))\b", re.I)
_SYSTEM = re.compile(r"^(?:check|run|do)\s+(?:the\s+)?(?:system|health)\b|^(?:system|health)\s+(?:check|status)\b", re.I)
_TASK = re.compile(r"^(?:list|show)\s+(?:my\s+|the\s+)?skills\b|^run (?:the )?skill\b", re.I)
_CODING = re.compile(r"^(?:review|refactor|debug|fix)\s+(?:the\s+|my\s+)?(?:code|bug|repo|function|script|tests?)\b|"
                     r"^explain (?:the |this |my )?code\b", re.I)

_ROLE_WORDS = "|".join(sorted(ROLE_NAMES, key=len, reverse=True))
_START_ROLE = re.compile(
    rf"^(?:start|run|launch|ask|tell|use|get|have)\s+(?:the\s+)?({_ROLE_WORDS})(?:\s+agent)?\b[\s,:-]*(?:to\s+)?(.*)$", re.I)
_ROLE_COLON = re.compile(rf"^({_ROLE_WORDS})(?:\s+agent)?\s*[,:-]\s*(.+)$", re.I)
_STOP_ROLE = re.compile(rf"^(?:stop|cancel|halt|kill)\s+(?:the\s+)?({_ROLE_WORDS})(?:\s+agent)?\s*$", re.I)
_START_TRADING = re.compile(r"\b(?:start|begin|resume|arm)\s+(?:live\s+)?trading\b", re.I)
_STOP_TRADING = re.compile(r"\b(?:stop|end|pause|halt|disarm)\s+(?:live\s+)?trading\b", re.I)

VERB = {"builder": "building", "coding": "working on", "research": "researching",
        "memory": "working on", "browser": "browsing for", "task": "handling", "system": "checking"}


def clean(text: str) -> str:
    t = (text or "").strip()
    t = _WAKE.sub("", t).strip()
    for _ in range(2):
        t = _POLITE.sub("", t).strip()
    return t.strip(" \t,.!")


def match(text: str) -> dict:
    raw = (text or "").strip()
    t = clean(raw)
    if not t:
        return {"intent": "chat", "text": raw}
    if _STOP_TRADING.search(t):
        return {"intent": "stop_trading"}
    if _START_TRADING.search(t):
        return {"intent": "start_trading"}
    m = _STOP_ROLE.match(t)
    if m:
        return {"intent": "stop_agent", "role": ROLE_NAMES[m.group(1).lower()]}
    m = _START_ROLE.match(t) or _ROLE_COLON.match(t)
    if m:
        role = ROLE_NAMES[m.group(1).lower()]
        goal = (m.group(2) or "").strip() or "Give a short status using available tools if helpful."
        if m.group(1).lower() == "build" and m.re is _START_ROLE:
            # "start build ..." -> builder
            role = "builder"
        return _agent(role, goal)
    if _NOTE.match(t):
        return _agent("memory", t)
    if _CODING.match(t):
        return _agent("coding", t)
    if _BUILD.match(t):
        return _agent("builder", t)
    if _RESEARCH.match(t):
        return _agent("research", t)
    if _BROWSE.match(t):
        return _agent("browser", t)
    if _SYSTEM.match(t):
        return _agent("system", t)
    if _TASK.match(t):
        return _agent("task", t)
    return {"intent": "chat", "text": raw}


def _agent(role: str, goal: str) -> dict:
    goal = goal.strip()
    if goal:
        goal = goal[0].upper() + goal[1:]
    return {"intent": "agent", "role": role, "goal": goal[:1000], "verb": VERB.get(role, "working on")}


def announce(role_name: str, verb: str, goal: str) -> str:
    g = re.sub(r"\s+", " ", goal or "").strip()
    if len(g) > 90:
        g = g[:87].rsplit(" ", 1)[0] + "…"
    return f"On it. {role_name} is {verb}: {g}"
