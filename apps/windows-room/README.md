# JARVIS Room (`windows-room`)

Local workshop shell: pywebview + a Three.js bay (OrbitControls, CSS2D plates). The window's JS API is `apps/windows-cc` `BridgeApi` — status, metrics, feed, memory, LLM probes, agents, `voice_turn` / `chat`, session, R3 workday, skills, brief. This folder does not reimplement those methods.

`Jarvis.exe` (Command Center) and `Jarvis3D.exe` are separate builds. `build_exe.ps1` writes only `apps\JarvisRoom.exe`.

The dated workshop plan and design (`docs/superpowers/plans/2026-11-04-jarvis-room-workshop.md`, `docs/superpowers/specs/2026-11-04-jarvis-room-workshop-design.md`) were not on `main` or `origin/jarvis/feat/command-center` when this app was added. Behavior follows the Command Center bridge and the Phase 1 desk's vendored three.js.

## Run from source

```powershell
cd apps\windows-room
pip install -r requirements.txt
pip install -r ..\windows-cc\requirements.txt
pip install -r ..\windows-panel\requirements.txt
$env:JARVIS_HOME = "C:\Users\rajk1\jarvis"
python host_main.py
```

WebView2 Evergreen is required on Windows (pywebview's Edge backend). The UI is served on `127.0.0.1` (`http_server=True`) so ES modules load. No remote UI URL.

## Voice

Talk calls `voice_turn` (listen, local ack inside the Command Center bridge, Gemini reply with OpenAI fallback). Typed lines call `chat`. The room speaks `reply` only. The captured transcript is shown on the voice plate and is not passed to `speak`.

## Plates

Each plate renders the latest bridge result. A failed call shows that error. Empty audit, missing skills, and `missing_key` LLM probes stay empty or failed — the UI does not substitute sample numbers.

## Vendor

`ui/vendor/` is a byte copy of `apps/windows-3d/ui/vendor/` (three.js r160, MIT, mrdoob/three.js). Addon imports use `./three.module.min.js`.

## Build (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\rajk1\jarvis\apps\windows-room\build_exe.ps1
```

Produces `apps\JarvisRoom.exe` and a Desktop shortcut **JARVIS Room**. Rebuild after UI, `host_main.py`, `room_api.py`, or the bundled Command Center / panel / `scripts/win` modules change.

## Tests

```bash
cd apps/windows-room
PYTHONPATH="../windows-cc:../windows-panel:../../scripts/win:." python -m unittest discover -s tests -v
```
