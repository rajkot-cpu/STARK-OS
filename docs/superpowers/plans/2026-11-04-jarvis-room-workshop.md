# JarvisRoom Workshop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `JarvisRoom.exe` — Three.js workshop room with live Command Center bridge + hybrid Gemini voice.

**Architecture:** New `apps/windows-room/` host reuses `apps/windows-cc/bridge_api.py` (sys.path). UI is Three.js (mrdoob/three.js CDN or vendored r160+) workshop scene with CSS2D plates calling `window.pywebview.api.*`.

**Tech Stack:** Python 3.11+, pywebview, PyInstaller onefile, Three.js, SpeechRecognition/PyAudio, pyttsx3, secrets/api_keys.env

## Global Constraints

- Local-only JARVIS_HOME `C:\Users\rajk1\jarvis`; never commit `secrets/api_keys.env`
- Honest empty states; no fake metrics
- R3 modal before `start_workday(true)`
- Desktop shortcut `JARVIS Room.lnk`; do not delete Jarvis.exe / Jarvis3D.exe

---

### Task 1: Scaffold windows-room host + bridge import

**Files:**
- Create: `apps/windows-room/host_main.py`
- Create: `apps/windows-room/requirements.txt`
- Create: `apps/windows-room/README.md`
- Test: `apps/windows-room/tests/test_import_bridge.py`

**Interfaces:**
- Produces: `discover_root() -> Path`, `main()` creates webview with `BridgeApi(root)`

- [ ] **Step 1:** Write test that imports BridgeApi via room path setup and calls `status` on a temp jarvis root with STATE.md + POLICY.yaml approved.

- [ ] **Step 2:** Implement `host_main.py` mirroring windows-cc (JARVIS_HOME, load_secrets, voice.load_prefs, js_api=BridgeApi).

- [ ] **Step 3:** Run `python -m unittest apps.windows-room.tests.test_import_bridge -v` → PASS

- [ ] **Step 4:** Commit `feat(room): scaffold host importing BridgeApi`

---

### Task 2: Three.js workshop scene + four plates

**Files:**
- Create: `apps/windows-room/ui/index.html`
- Create: `apps/windows-room/ui/css/room.css`
- Create: `apps/windows-room/ui/js/bridge.js` (copy whenReady/call from windows-cc)
- Create: `apps/windows-room/ui/js/scene.js`
- Create: `apps/windows-room/ui/js/app.js`
- Vendor or CDN: three.js + OrbitControls + CSS2DRenderer (prefer vendor under `ui/vendor/` for offline)

**Interfaces:**
- Consumes: bridge `call(method,...args)`
- Produces: plates Status / Voice / AgentsLLM / Feed updated by `refresh()`

- [ ] **Step 1:** Build dark workshop mesh (floor, walls, desk box, cyan/gold emissive accents).

- [ ] **Step 2:** CSS2D plates with live bindings; poll every 3s after pywebviewready.

- [ ] **Step 3:** Wire voice_turn on mic button; show reply text; no “You said …” echo.

- [ ] **Step 4:** Commit `feat(room): three.js workshop UI with live plates`

---

### Task 3: Actions + R3 + skills strip

**Files:**
- Modify: `apps/windows-room/ui/js/app.js`
- Modify: `apps/windows-room/ui/index.html`

- [ ] **Step 1:** Buttons: Session Start, Dry-run, Mute, Start Workday → R3 modal → `start_workday(true)`.

- [ ] **Step 2:** Skills list from `skills()` on Status plate footer.

- [ ] **Step 3:** Agent start/stop buttons on Agents plate.

- [ ] **Step 4:** Commit `feat(room): wire CC actions and R3`

---

### Task 4: PyInstaller JarvisRoom.exe + chandan install

**Files:**
- Create: `apps/windows-room/build_exe.ps1`
- Output: `C:\Users\rajk1\jarvis\apps\JarvisRoom.exe`
- Shortcut: Desktop `JARVIS Room.lnk`

- [ ] **Step 1:** Spec mirrors windows-cc hiddenimports (bridge_api, chat, stt, pyaudio, voice, agents, …) + `--add-data ui;ui` + paths to windows-cc and windows-panel.

- [ ] **Step 2:** Build on chandan; kill locking processes; copy exe; create shortcut.

- [ ] **Step 3:** Smoke: launch, status ok, speak ack path, Gemini voice_turn once.

- [ ] **Step 4:** Commit `feat(room): PyInstaller JarvisRoom.exe`

---

### Task 5: Docs + STARK-OS push

- [ ] Update README; push branch to `stark` remote (rajkot-cpu/STARK-OS).

- [ ] Commit `docs(room): workshop phase1 done checklist`
