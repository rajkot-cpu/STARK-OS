# JARVIS Safety & Governance (Master Upgrade — Phase 1 / Module 1)

## Emergency STOP — four ways
| Trigger | How |
|---|---|
| Global hotkey | **Ctrl+Alt+Shift+S** (works while Jarvis is minimised; Win32 `RegisterHotKey`) |
| Command | Type or say `stop`, `Jarvis stop`, `stop everything`, `emergency stop`, `halt` |
| STOP file | Create an empty file named `STOP` in the Jarvis folder: `C:\Users\rajk1\jarvis\STOP` (checked every second) |
| Dashboard | Red **EMERGENCY STOP** button in the top bar, or *Safety & STOP → Initiate STOP* |

What STOP does: refuses new agent runs, shell commands, R3 confirmations, screen reads and the workday
start; cancels pending approval requests and saved agent loops (queued actions); stops all 8 agents,
kills their shell and ffmpeg child processes, stops the wake word and speech. Trading: no trading
module exists in this build (reserved `start trading` still does nothing). Logs and state are kept.
The STOP state is saved in `logs\halt_state.json`, so restarting Jarvis keeps it stopped.

**Resume** — only by you: delete any `STOP` file, then type `RESUME` (Resume button) or type `resume`
in the command bar. Voice cannot resume. Stopped tasks are never restarted automatically.

Config flags (`config\cc_settings.json`, file-only — the UI and agents cannot change them):
`"stop_hotkey": true`, `"stop_file_watch": true`.

## Permission levels → existing tiers (nothing weakened)
| Doc level | Tier | Rule |
|---|---|---|
| 1 Read only | R1 | automatic, logged |
| 2 Routine automation | R2 | automatic, reversible, logged |
| 3 Controlled external actions | R3 | your confirmation every time |
| 4 High-risk (money, live trades, deletes, security) | R4 | typed confirmation every time; live trading also needs a separate approval and is **not enabled** |
Unknown actions map to Level 4. Source: `apps/windows-cc/permissions.py`.

## Audit log (tamper-evident)
`logs\audit.jsonl` lines written by Jarvis carry `prev` (hash of the previous line) and `hash`.
Check: `python apps\windows-cc\audit_chain.py logs\audit.jsonl` (exit 0 = intact) or *Safety → Re-check*.

## API keys
Lookup order: environment → Windows Credential Manager (`JARVIS/<KEY>`) → `secrets\api_keys.env`.
Migrate: `python apps\windows-cc\secrets_store.py migrate C:\Users\rajk1\jarvis` — every key is written
and read back; only if all verify are the values removed from the file (names kept as comments).
Undo: put `KEY=VALUE` lines back in `api_keys.env`. Values are never printed.

## Crash diagnostics
`logs\session.json` (pid, start, heartbeat with memory every 30 s, clean-exit flag),
`logs\crash-native.log` (faulthandler native crashes), `logs\ui-errors.log` (reports a previous
session that ended without a clean exit).
