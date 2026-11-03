# Jarvis.exe — 3D icons + live tool-using agents

**Date:** 2026-11-04  
**Status:** Approved (Chandan)  
**Target:** Update installed `Jarvis.exe` (Command Center) only. JarvisRoom / Jarvis3D stay uninstalled.

## Goals

1. Replace flat text sidebar with **Three.js 3D icon meshes** and upgrade the home AI Core to a real Three.js holographic sphere.
2. Make all **six fixed agents** (Coding, Research, Memory, Browser, Task, System) **live**: each calls Gemini with its role prompt and can use real tools.
3. Keep hybrid voice, chat, session/workday, R3, metrics, feed, memory, LLM probes, skills list as they work today.

## Non-goals (this release)

- Separate Room / 3D desk exes
- Image generation / multimodal creative pack
- Full calendar/email productivity integrations
- Parallel agent daemon process
- Expanding agent tools beyond the sandbox listed below

## Approach

**A — Evolve Command Center** (chosen): stay in `apps/windows-cc`, vendor Three.js into `ui/vendor/`, extend `bridge_api` + `agents/worker.py`. Reuse existing Gemini key loader (`secrets/api_keys.env`).

## Architecture

```
Jarvis.exe (pywebview host_main)
  └── ui/ (HTTP)
        ├── index.html / hud.css / app.js / bridge.js
        ├── icons3d.js     # small Three.js canvases per nav button
        ├── core3d.js      # replaces sphere.js 2D canvas
        └── vendor/three*  # from windows-room / windows-3d offline copies
  └── bridge_api.py
        └── agents/worker.py  # Gemini + tool loop (no heartbeat stub)
        └── agent_tools.py    # sandboxed tools
```

Override note: earlier CC design kept 3D as a separate optional exe. **This spec overrides that** — 3D icons/core live inside Jarvis.exe.

## UI — 3D icons

- Each sidebar `data-route` button hosts a small WebGL canvas (~28–36px) with a cyan wire/glow mesh (Stark palette: bg `#04070b`, cyan `#38d4ff`, gold only for Mute/Quiet/R3).
- Icon set (one mesh motif each): home/core, agents, tasks, calendar, memory, conversations, knowledge, skills, workflows.
- Click still uses existing route buttons; canvas is decorative + hover pulse, not a separate hit target unless needed for accessibility (button remains the control).
- Home AI Core: replace `sphere.js` 2D ellipses with Three.js scene (slow rotate, cyan wire sphere, optional particle ring). No orbit drag required on home (keep UI calm); optional idle animation only.
- Fallbacks: if WebGL unavailable, show CSS cyan glyph + existing layout (no blank sidebar).

## Agents — live + tools

### Roles (unchanged six)

| Agent    | Focus |
|----------|--------|
| Coding   | Code/scripts under jarvis root |
| Research | Web fetch + summarize |
| Memory   | Memory index / STATE notes |
| Browser  | Fetch/read public URLs |
| Task     | Skills list/run orchestration |
| System   | Metrics, status, POLICY-aware summaries |

### Runtime

- Replace `worker._run` heartbeat with a loop: take optional goal from UI → Gemini (`gemini-3.1-flash-lite-preview`, same as chat) with role system prompt → tool calls until done or max steps (e.g. 8).
- Persist last status, last reply, and tool step log for Agents page + Live Feed.
- `missing_key` / provider error: surface honestly; do not fabricate results.
- Start/stop via existing `agent_start` / `agent_stop`.

### Tools (sandbox)

| Tool | Behavior | Risk |
|------|----------|------|
| `list_dir` | List under jarvis root only | R1 |
| `read_file` | Read text file under jarvis root; block path escape | R1 |
| `web_fetch` | GET http(s) URL; size/time limits; no auth cookies | R2 |
| `skills_list` | Existing skills bridge | R1 |
| `skill_run` | Run allowed skill by name | R2; R3 if skill marked high-risk |
| Writes / deletes / `start_workday` | Not agent-autonomous | R3 via existing UI |

Jarvis root = install/workspace root used by host today (`C:\Users\rajk1\jarvis` on chandan). Resolve realpath; reject `..` escapes.

## Data flow

1. UI Start Agent → `bridge.agent_start(id, goal?)`.
2. Worker thread runs Gemini+tools; pushes events to feed + in-memory agent state.
3. UI polls `agents` / feed as today; Agents page shows steps + last reply.
4. Stop cancels cooperative flag between tool steps.

## Errors

- No key → status `missing_key`, idle.
- Path escape / oversized fetch → tool error string to agent log + feed.
- Gemini timeout/404 → retry once with same model; then error status (no silent fallback to fake heartbeat).

## Testing

- Unit: path sandbox reject outside root; tool registry; worker stop flag; missing_key short-circuit.
- Manual after rebuild: icons visible, core animates, start Research with a fetch goal, see steps in UI, R3 still on Start Workday.

## Ship

- Rebuild with existing `apps/windows-cc/build_exe.ps1` → `C:\Users\rajk1\jarvis\apps\Jarvis.exe` + Desktop `JARVIS.lnk`.
- Do not reinstall JarvisRoom.exe / Jarvis3D.exe.

## Success criteria

- [ ] Sidebar shows Three.js icons for all nav routes (or CSS fallback).
- [ ] Home AI Core is Three.js (not 2D ellipse canvas).
- [ ] All six agents can run a Gemini turn with at least one tool when key present.
- [ ] Path sandbox blocks escape in tests.
- [ ] Voice/chat/workday/R3 still work; Jarvis.exe refreshed on chandan.
