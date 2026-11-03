# Jarvis.exe 3D icons + live tool-using agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update installed Jarvis.exe so the Command Center sidebar uses Three.js 3D icons, the home AI Core is a Three.js sphere, and all six agents run Gemini with sandboxed tools instead of heartbeats.

**Architecture:** Evolve `apps/windows-cc` only. Add `agent_tools.py` (path sandbox + web_fetch + skills). Rewrite `AgentHub._run` to a Gemini tool loop. Vendor Three.js from `apps/windows-room/ui/vendor/` into `apps/windows-cc/ui/vendor/`. New `icons3d.js` / `core3d.js`; keep pywebview host and bridge.

**Tech Stack:** Python 3.13, unittest, urllib Gemini API (`gemini-3.1-flash-lite-preview`), Three.js (offline module already in windows-room), pywebview, PyInstaller.

## Global Constraints

- Ship target is **Jarvis.exe** only; do not reinstall JarvisRoom.exe or Jarvis3D.exe.
- Stark palette: bg `#04070b`, panel `#0b2233`, cyan `#38d4ff`, text `#e4f6ff`, gold `#ff9d2e` (Mute/Quiet/R3 only), muted `#7a8fa8`, danger `#ff3b30`, ok `#3dff9a`.
- Jarvis root sandbox = `AgentHub.root` / bridge `self.root` (on chandan: `C:\Users\rajk1\jarvis`).
- Gemini model: `gemini-3.1-flash-lite-preview` (same as `chat.py`).
- Max tool loop steps per start: **8**.
- Writes/deletes/`start_workday` are **not** agent tools; R3 stays on existing UI.
- Never invent tool results; surface `missing_key` honestly.
- Worktree: `/home/box/jarvis/.worktrees/jarvis/feat/command-center` on branch `jarvis/feat/command-center`.
- Spec: `docs/superpowers/specs/2026-11-04-jarvis-cc-3d-live-agents-design.md`.

## File map

| File | Role |
|------|------|
| Create `apps/windows-cc/agent_tools.py` | Sandboxed tools |
| Create `apps/windows-cc/tests/test_agent_tools.py` | Tool sandbox tests |
| Modify `apps/windows-cc/agents/registry.py` | Align tools + prompts with real tools |
| Modify `apps/windows-cc/agents/worker.py` | Gemini + tool loop; steps/log |
| Modify `apps/windows-cc/tests/test_agents.py` | Cover missing_key + stop mid-run |
| Modify `apps/windows-cc/bridge_api.py` | Optional goal on `agent_start`; pass feed hook if needed |
| Create `apps/windows-cc/ui/vendor/` | Copy three.module.js (+ LICENSE) from windows-room |
| Create `apps/windows-cc/ui/js/icons3d.js` | Per-nav Three.js icon canvases |
| Create `apps/windows-cc/ui/js/core3d.js` | Home AI Core Three.js scene |
| Modify `apps/windows-cc/ui/index.html` | Script tags; icon canvas slots in nav |
| Modify `apps/windows-cc/ui/css/hud.css` | Icon canvas sizing |
| Modify `apps/windows-cc/ui/js/app.js` | Init icons/core; show agent steps |
| Modify `apps/windows-cc/build_exe.ps1` | Hidden-import `agent_tools` |
| Keep `apps/windows-cc/ui/js/sphere.js` | Unused after core3d; can leave or delete in last task |

---

### Task 1: Sandboxed agent tools

**Files:**
- Create: `apps/windows-cc/agent_tools.py`
- Create: `apps/windows-cc/tests/test_agent_tools.py`

**Interfaces:**
- Consumes: `pathlib.Path`
- Produces:
  - `class AgentTools:`
    - `__init__(self, root: Path)`
    - `safe_path(self, rel_or_abs: str) -> Path` — raises `ValueError` if outside root
    - `list_dir(self, rel: str = ".") -> dict` — `{"ok": True, "entries": [{"name","is_dir"}]}` or error
    - `read_file(self, rel: str, max_bytes: int = 100_000) -> dict`
    - `web_fetch(self, url: str, max_bytes: int = 200_000, timeout: float = 15.0) -> dict`
    - `skills_list(self) -> dict` — scan `root/skills` for `*/SKILL.md` names (or empty list)
    - `skill_run(self, name: str) -> dict` — for this release return `{"ok": False, "error": "skill_run deferred: use Skills tab"}` **unless** a tiny allowlisted dry skill exists; prefer stub that lists only (YAGNI: implement list; skill_run returns explicit not-implemented with ok False) — **Spec says skill_run allowed R2.** Implement: if `skills/<name>/SKILL.md` exists, return `{"ok": True, "data": {"name", "path", "preview": first 500 chars}}` (read-only preview = safe R1/R2). Do **not** execute shell.
  - `TOOL_SCHEMAS: list[dict]` — Gemini functionDeclarations for the five tools above

- [ ] **Step 1: Write failing tests**

```python
# apps/windows-cc/tests/test_agent_tools.py
import sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))
from agent_tools import AgentTools

class TestAgentTools(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("hi", encoding="utf-8")
            tools = AgentTools(root)
            with self.assertRaises(ValueError):
                tools.safe_path("../outside.txt")
            with self.assertRaises(ValueError):
                tools.safe_path(str(Path(td).parent / "x"))

    def test_read_file_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("hello", encoding="utf-8")
            r = AgentTools(root).read_file("ok.txt")
            self.assertTrue(r["ok"])
            self.assertEqual(r["data"]["text"], "hello")

    def test_web_fetch_rejects_non_http(self):
        with tempfile.TemporaryDirectory() as td:
            r = AgentTools(Path(td)).web_fetch("file:///etc/passwd")
            self.assertFalse(r["ok"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — expect FAIL (import error)**

Run: `cd /home/box/jarvis/.worktrees/jarvis/feat/command-center && python -m unittest apps.windows-cc.tests.test_agent_tools -v`  
(or `python apps/windows-cc/tests/test_agent_tools.py -v`)  
Expected: FAIL `ModuleNotFoundError: agent_tools`

- [ ] **Step 3: Implement `agent_tools.py`**

```python
# apps/windows-cc/agent_tools.py
from __future__ import annotations
import json, urllib.error, urllib.request
from pathlib import Path

TOOL_SCHEMAS = [
    {"name": "list_dir", "description": "List files under JARVIS root", "parameters": {"type": "object", "properties": {"rel": {"type": "string"}}, "required": []}},
    {"name": "read_file", "description": "Read a text file under JARVIS root", "parameters": {"type": "object", "properties": {"rel": {"type": "string"}}, "required": ["rel"]}},
    {"name": "web_fetch", "description": "HTTP GET a public URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "skills_list", "description": "List skill folder names", "parameters": {"type": "object", "properties": {}}},
    {"name": "skill_run", "description": "Preview a skill SKILL.md (read-only)", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]

class AgentTools:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def safe_path(self, rel_or_abs: str) -> Path:
        p = (self.root / rel_or_abs).resolve() if not Path(rel_or_abs).is_absolute() else Path(rel_or_abs).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path outside jarvis root: {rel_or_abs}")
        return p

    def list_dir(self, rel: str = ".") -> dict:
        try:
            d = self.safe_path(rel)
            if not d.is_dir():
                return {"ok": False, "error": "not a directory"}
            entries = [{"name": c.name, "is_dir": c.is_dir()} for c in sorted(d.iterdir())[:200]]
            return {"ok": True, "data": {"entries": entries}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_file(self, rel: str, max_bytes: int = 100_000) -> dict:
        try:
            p = self.safe_path(rel)
            if not p.is_file():
                return {"ok": False, "error": "not a file"}
            data = p.read_bytes()[:max_bytes]
            return {"ok": True, "data": {"path": str(p), "text": data.decode("utf-8", errors="replace")}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def web_fetch(self, url: str, max_bytes: int = 200_000, timeout: float = 15.0) -> dict:
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "error": "only http(s) allowed"}
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "JARVIS-Agent/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            text = raw[:max_bytes].decode("utf-8", errors="replace")
            return {"ok": True, "data": {"url": url, "text": text, "truncated": truncated}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def skills_list(self) -> dict:
        skills = self.root / "skills"
        if not skills.is_dir():
            return {"ok": True, "data": {"skills": []}}
        names = sorted([p.name for p in skills.iterdir() if p.is_dir() and (p / "SKILL.md").exists()])
        return {"ok": True, "data": {"skills": names}}

    def skill_run(self, name: str) -> dict:
        if "/" in name or "\\" in name or ".." in name:
            return {"ok": False, "error": "invalid skill name"}
        p = self.root / "skills" / name / "SKILL.md"
        try:
            self.safe_path(str(p))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not p.is_file():
            return {"ok": False, "error": "skill not found"}
        preview = p.read_text(encoding="utf-8", errors="replace")[:500]
        return {"ok": True, "data": {"name": name, "path": str(p), "preview": preview}}

    def call(self, name: str, args: dict) -> dict:
        if name == "list_dir":
            return self.list_dir(args.get("rel") or ".")
        if name == "read_file":
            return self.read_file(args["rel"])
        if name == "web_fetch":
            return self.web_fetch(args["url"])
        if name == "skills_list":
            return self.skills_list()
        if name == "skill_run":
            return self.skill_run(args["name"])
        return {"ok": False, "error": f"unknown tool {name}"}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python apps/windows-cc/tests/test_agent_tools.py -v`  
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add apps/windows-cc/agent_tools.py apps/windows-cc/tests/test_agent_tools.py
git commit -m "feat(cc): sandboxed agent tools (list/read/fetch/skills)"
```

---

### Task 2: Live AgentHub (Gemini + tools)

**Files:**
- Modify: `apps/windows-cc/agents/registry.py`
- Modify: `apps/windows-cc/agents/worker.py`
- Modify: `apps/windows-cc/tests/test_agents.py`
- Modify: `apps/windows-cc/bridge_api.py` (`agent_start` optional goal)

**Interfaces:**
- Consumes: `AgentTools`, `TOOL_SCHEMAS`, `llm_providers.load_secrets` / `_resolve_key`, role prompts
- Produces:
  - `AgentHub.start(role_id: str, goal: str | None = None) -> dict`
  - `list()` rows include `steps: list[str]` (last run) and `detail` / `last_reply`
  - `BridgeApi.agent_start(role_id: str, goal: str = "") -> dict`

- [ ] **Step 1: Update registry tools to match real tools**

Set each role's `tools` to a subset of `list_dir,read_file,web_fetch,skills_list,skill_run` appropriate to the role (coding: list_dir+read_file; research/browser: web_fetch; memory: list_dir+read_file under memory/; task: skills_*; system: list_dir+read_file). Keep six ids unchanged.

- [ ] **Step 2: Extend failing test for missing key short-circuit**

```python
def test_start_without_gemini_key_sets_error(self):
    with tempfile.TemporaryDirectory() as td:
        hub = AgentHub(root=Path(td), secrets={})  # no GEMINI_API_KEY
        hub.start("research", goal="fetch example")
        import time; time.sleep(0.5)
        row = next(a for a in hub.list() if a["id"] == "research")
        self.assertIn(row["state"], ("error", "standby", "active"))
        # After loop exits on missing key:
        self.assertTrue("missing_key" in (row.get("detail") or "") or row["state"] == "error" or "missing_key" in (row.get("last_reply") or ""))
```

Adjust assertion to match implementation: preferred final state `error` with detail `missing_key`.

- [ ] **Step 3: Rewrite `worker.py`**

Key behavior:
- `__init__(self, root, secrets: dict | None = None, feed_append=None)`
- Load secrets via `load_secrets(self.root)` if secrets is None
- `_run(role_id)`:
  1. Resolve Gemini key; if missing → `_state=error`, `_detail=missing_key`, return
  2. Build system prompt from `ROLES` entry
  3. User message = goal or default `"Give a one-paragraph status using available tools if helpful."`
  4. Loop up to 8 steps: call Gemini with `tools=TOOL_SCHEMAS` filtered to role tools; on `functionCall` run `AgentTools.call` and append step string; on final text set `last_reply` and break
  5. Respect `_stop` between steps
  6. On success `_state=standby` (one-shot run) OR stay active until stop — **Spec: start/stop.** Prefer **one-shot**: start runs one goal loop then returns to `standby` with last_reply preserved; stop aborts mid-loop.

Gemini function-calling via REST (functionDeclarations under `tools: [{functionDeclarations: ...}]`). If function calling is awkward with urllib, acceptable MVP: single Gemini text call that asks for JSON `{"tool":"...","args":{...}}` then one more call with tool result — document in commit. Prefer native functionDeclarations.

Also update `list()` to return `steps` and `last_reply`.

- [ ] **Step 4: Bridge `agent_start(self, role_id: str, goal: str = "")`**

Pass `goal` into `hub.start`. Construct hub with secrets from existing loader used by chat.

- [ ] **Step 5: Run unit tests**

```bash
python apps/windows-cc/tests/test_agent_tools.py -v
python apps/windows-cc/tests/test_agents.py -v
```
Expected: PASS (network not required for missing_key / start-stop)

- [ ] **Step 6: Commit**

```bash
git add apps/windows-cc/agents/registry.py apps/windows-cc/agents/worker.py apps/windows-cc/tests/test_agents.py apps/windows-cc/bridge_api.py
git commit -m "feat(cc): live Gemini agents with tool loop"
```

---

### Task 3: Three.js vendor + 3D sidebar icons

**Files:**
- Create: `apps/windows-cc/ui/vendor/three.module.js` (copy)
- Create: `apps/windows-cc/ui/vendor/LICENSE` (copy)
- Create: `apps/windows-cc/ui/js/icons3d.js`
- Modify: `apps/windows-cc/ui/index.html`
- Modify: `apps/windows-cc/ui/css/hud.css`
- Modify: `apps/windows-cc/ui/js/app.js` (init call)

**Interfaces:**
- Produces: `export function mountNavIcons(navEl: HTMLElement): void` — finds `button[data-route]`, injects canvas, draws motif by route; no-ops if WebGL missing

- [ ] **Step 1: Copy vendor**

```bash
mkdir -p apps/windows-cc/ui/vendor
cp apps/windows-room/ui/vendor/three.module.js apps/windows-cc/ui/vendor/
cp apps/windows-room/ui/vendor/LICENSE apps/windows-cc/ui/vendor/
```

- [ ] **Step 2: Implement `icons3d.js`**

For each route, create canvas 32x32 inside the button; Scene + PerspectiveCamera + WebGLRenderer(alpha); cyan Mesh (Box/Octahedron/Torus/etc. per route map); requestAnimationFrame slow rotate. On WebGL context failure, set `button.dataset.iconFallback = "1"` and add CSS class `icon-fallback` with unicode/cyan square via CSS.

- [ ] **Step 3: HTML/CSS**

Wrap button label; style `canvas.nav-icon { width:28px; height:28px; vertical-align:middle; margin-right:8px; }`

- [ ] **Step 4: Call `mountNavIcons` from `app.js` on boot**

- [ ] **Step 5: Commit**

```bash
git add apps/windows-cc/ui/vendor apps/windows-cc/ui/js/icons3d.js apps/windows-cc/ui/index.html apps/windows-cc/ui/css/hud.css apps/windows-cc/ui/js/app.js
git commit -m "feat(cc): Three.js 3D sidebar nav icons"
```

---

### Task 4: Three.js AI Core + agents UI steps

**Files:**
- Create: `apps/windows-cc/ui/js/core3d.js`
- Modify: `apps/windows-cc/ui/js/app.js` (replace `drawSphere` usage; render agent steps)
- Modify: `apps/windows-cc/ui/index.html` (script type=module if needed)
- Optional: stop importing `sphere.js`

**Interfaces:**
- Produces: `export function mountCore(canvas: HTMLCanvasElement): { setHealth(n: number): void, dispose(): void }`

- [ ] **Step 1: Implement core3d** — wireframe SphereGeometry, cyan materials, idle rotation, `setHealth` adjusts emissive intensity

- [ ] **Step 2: Wire home canvas `#sphere` to `mountCore`**

- [ ] **Step 3: Update `renderAgents`** to show `last_reply` and last 5 `steps` under each card; optional goal input calling `agent_start` with goal string

- [ ] **Step 4: Manual browser check** — open `ui/index.html` via host if possible; else visual review after rebuild

- [ ] **Step 5: Commit**

```bash
git add apps/windows-cc/ui/js/core3d.js apps/windows-cc/ui/js/app.js apps/windows-cc/ui/index.html
git commit -m "feat(cc): Three.js AI Core + agent step UI"
```

---

### Task 5: PyInstaller + install on chandan

**Files:**
- Modify: `apps/windows-cc/build_exe.ps1` — add `--hidden-import agent_tools`
- Sync sources / rebuild on machine `754b28ed-520b-4dfa-a053-02a9ab8d245b`

- [ ] **Step 1: Update build script hidden-imports**

- [ ] **Step 2: Commit**

```bash
git add apps/windows-cc/build_exe.ps1
git commit -m "build(cc): include agent_tools in Jarvis.exe"
```

- [ ] **Step 3: Sync `apps/windows-cc` to `C:\Users\rajk1\jarvis\` (tar or CopyFromBox)**

- [ ] **Step 4: Kill Jarvis.exe if running; run `build_exe.ps1`; confirm `C:\Users\rajk1\jarvis\apps\Jarvis.exe` refreshed; launch smoke

- [ ] **Step 5: Verify checklist from spec** (icons, core, one agent with key, R3 workday still works)

---

## Spec coverage self-check

| Spec requirement | Task |
|------------------|------|
| Three.js nav icons | Task 3 |
| Three.js AI Core | Task 4 |
| Six live Gemini agents + tools | Task 2 (+ tools Task 1) |
| Path sandbox tests | Task 1 |
| R3 unchanged / no write tools | Task 1–2 |
| Rebuild Jarvis.exe only | Task 5 |
| missing_key honest | Task 2 |
| WebGL fallback | Task 3 |

## Placeholder scan

None intentional. `skill_run` is read-only preview (explicit), not shell exec.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-11-04-jarvis-cc-3d-live-agents.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
**2. Inline Execution** — this session with executing-plans + checkpoints
