# JARVIS Room Workshop (Phase 1) — Design

Date: 2026-11-04  
Status: Approved by intent (user: 3D installed Jarvis, all functions live, GH high-star patterns)  
Owner: Dr Chandan kumar / IRON MAN · JARVIS  
Host: Windows `chandan` (`C:\Users\rajk1\jarvis`)

## Goal

Ship **`JarvisRoom.exe`**: Iron Man workshop holographic room (WebView2 + **Three.js**) with floating HUD plates and **all Command Center bridge functions live** (status, metrics, feed, memory, LLMs, agents, skills, session/workday R3, hybrid voice). Keep existing **`Jarvis.exe`** (flat CC) and **`Jarvis3D.exe`** (Phase‑1 desk).

## GitHub references (patterns only — no wholesale copy)

| Repo | Stars (approx) | Use |
|---|---|---|
| [mrdoob/three.js](https://github.com/mrdoob/three.js) | ~117k | Scene, OrbitControls, CSS2DRenderer, lighting |
| Existing STARK-OS `apps/windows-3d` | — | Desk plate layout baseline |
| Existing STARK-OS `apps/windows-cc` | — | BridgeApi, chat/voice_turn, secrets |

Do not invent live telemetry. Do not ship copyrighted Iron Man assets.

## Decisions

| Decision | Choice |
|---|---|
| Package | New `JarvisRoom.exe` |
| Keep | `Jarvis.exe` + `Jarvis3D.exe` |
| Voice | Hybrid: local “Yes sir” + Gemini (`chat.voice_turn`) |
| Plates | Status, Voice, Agents/LLMs, Live Feed (+ skills list in Status actions) |
| Backend | Reuse windows-cc `BridgeApi` (+ panel_api) |
| Secrets | `secrets/api_keys.env` via `load_secrets` |
| Desktop shortcut | `JARVIS Room.lnk` |

## Architecture

```
JarvisRoom.exe
  host_main.py (pywebview)
    BridgeApi (from windows-cc)  ← full function surface
    ui/ (Three.js workshop + CSS2D plates)
```

## Bridge surface (must work)

status, metrics, feed, memory, llms, agents, agent_start/stop, listen, speak, mute, voice_turn, chat, session_start, dry_run_workday, start_workday(R3), brief, skills

## Out of scope (Phase 1)

Suit-bay / full room-scale cinema; hand tracking; replacing Jarvis.exe; OpenAI required (Gemini primary).

## Success

Double-click `JarvisRoom.exe` → 3D workshop; plates show live data; Tap Speak → ack + Gemini reply; Session/Dry-run/R3 workday work; mute works.
