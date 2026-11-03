# Jarvis.exe — Voice Trading + API Keys + Agents (Approach A)

**Status:** draft for user review  
**Date:** 2026-11-04 (Asia/Calcutta)  
**Host:** Jarvis Command Center (`apps/windows-cc` → `Jarvis.exe`)  
**Approach:** A — Voice intents + Secrets UI + Trading bridge (not deep-embed OptionsTrd)

## Goal

When Chandan says “Jarvis, start trading” on this PC, Jarvis arms a **live** trading session. Confirmed orders go through **Sahi via OptionsTrd**. Agents (including a new Trading role) run properly with Gemini preferred and OpenAI fallback. An in-app **API Keys** page lets him add LLM keys and named slots (e.g. Sahi) without editing files by hand.

## Non-goals (this release)

- Embedding OptionsTrd / broker engine inside Jarvis.exe
- Silent or auto-sent live orders (voice alone never places an order)
- Free-form arbitrary env keys beyond named slots + LLM set
- Continuous always-on wake word (keep push-to-talk / Tap to Speak)

## Locked choices

| Topic | Choice |
|-------|--------|
| Release scope | All three: API Keys UI + voice trading + agents |
| “Start trading” | Live armed mode; real orders only after typed R4 each time |
| Order path | Sahi via OptionsTrd workflow |
| API Keys page | LLM providers + named slots (not free-form) |
| Agents bar | Gemini key path + OpenAI fallback + Trading agent |

## Architecture

Three modules on the existing pywebview bridge:

1. **`voice_intents`** — After STT, match known phrases before free chat. Unmatched text still uses existing Gemini/OpenAI chat.
2. **`secrets` bridge + API Keys UI** — Read/write `JARVIS_ROOT/secrets/api_keys.env` for fixed LLM keys and named slots. Masked list in UI; never log raw values; reload env after save.
3. **`trading_session`** — Voice `start trading` arms session and notifies OptionsTrd for desk context. Any order draft requires typed R4 (`CONFIRM`) in UI before Sahi-bound submit. `stop trading` or process exit disarms. New **Trading** agent drafts/researches only — cannot bypass R4.

AgentHub: prefer Gemini native tool loop; if no Gemini key, OpenAI fallback for agent runs.

## Components & data flow

### Voice

`voice_turn` → normalize transcript → `match_intent` →

- `start_trading` → `trading_session.arm()` + TTS ack  
- `stop_trading` → `trading_session.disarm()` + TTS ack  
- else → existing chat reply + speak  

Low-confidence / ambiguous phrases fall through to chat (no accidental arm).

### API Keys UI

- New nav route: **API Keys**
- Bridge: `secrets_list` (masked), `secrets_set(name, value)`, `secrets_clear(name)`
- Slots (initial):
  - `JARVIS_OPENAI_API_KEY`
  - `JARVIS_GEMINI_API_KEY`
  - `JARVIS_ANTHROPIC_API_KEY`
  - `JARVIS_GROQ_API_KEY`
  - `JARVIS_SAHI_CLIENT_ID`
  - `JARVIS_SAHI_CLIENT_SECRET`
  - `JARVIS_SAHI_ACCESS_TOKEN` (or equivalent named Sahi slot set documented in UI)
- Writes only under `secrets/api_keys.env` (create from template if missing)
- After save: update `os.environ` for those keys (overwrite allowed for explicit user save) and refresh LLM probes

### Trading session

- In-memory armed flag + audit lines in `logs/audit.jsonl` for arm / disarm / order_attempt / confirm / reject
- Order path: Trading agent or UI drafts ticket → UI shows ticket → user types `CONFIRM` (R4) → bridge hands payload to OptionsTrd/Sahi binder
- Disarmed session rejects order attempts with a clear error
- Missing OptionsTrd/Sahi bind: arm still succeeds; submit returns “desk not linked” (no fake fills)

### Agents

- Registry adds role `trading` (draft/research; capital preservation; never claim an order was sent without R4 receipt)
- Worker: Gemini tool loop if key present; else OpenAI fallback
- Read-only tool `trading_status` (armed?, last audit summary) for agents
- Existing tools (shell R3, code_search, memory_note, …) unchanged

## Errors & safety

- Bad/empty API key → probe `missing_key` / `auth_error`; agent start refuses with that message
- Intent misfire → fall through to chat
- Wrong R4 string → cancel; audit reject
- POLICY / JARVIS.md: money movement stays R4; silence is never consent
- Secrets values never appear in Live Feed, agent step text, or audit beyond key *names*

## Testing

- Unit: intent matcher (`start/stop trading` variants)
- Unit: secrets round-trip in temp dir (no real keys in repo)
- Unit: trading_session arm/disarm; reject order without confirm; reject when disarmed
- Unit: AgentHub OpenAI fallback when Gemini empty; Trading role listed
- Rebuild Jarvis.exe on chandan; launch smoke; manual: save a key in UI (masked), voice arm/disarm ack, Agents pane starts with keyed provider

## Success criteria

1. User can paste Gemini (and other named keys) in Jarvis UI; tiles flip off `missing_key` after save/restart-or-reload.
2. Saying “start trading” (via Tap to Speak) arms live session and speaks confirmation; “stop trading” disarms.
3. No live order leaves the machine without typed `CONFIRM`.
4. Trading agent appears and runs tool loops with Gemini or OpenAI.
5. Audit log records arm/disarm/confirm/reject.

## Implementation notes

- Keep work on a feature branch / worktree under `apps/windows-cc`
- PyInstaller: add any new modules to hiddenimports in `build_exe.ps1`
- OptionsTrd integration for this release = bridge/handoff contract + message/ping; deep order API details may stub to “desk not linked” until binder credentials exist — still ship R4 UI path
