# Changelog

## 2026-11-18 — Master Upgrade Phase 1: Safety & Governance (branch `jarvis-upgrade`)
Backup before changes: `C:\Users\rajk1\jarvis-backups\jarvis-pre-upgrade-20261118-005811.zip`
(663 files, 1.03 GB; excludes the older `backups\` copy, old `Jarvis.exe.bak-*` files, build/dist and `__pycache__`).
Previous exe kept as `apps\Jarvis.exe.bak-20261118-prephase1`.

Added
- `apps/windows-cc/halt.py` — Emergency STOP controller (persistent state, STOP-file watcher, handlers, child-process kill, no auto-resume, typed RESUME).
- `apps/windows-cc/hotkey_win.py` — global Ctrl+Alt+Shift+S.
- `apps/windows-cc/audit_chain.py` — hash-chained audit lines + verifier CLI.
- `apps/windows-cc/secrets_store.py` — Windows Credential Manager store + verified migration.
- `apps/windows-cc/session_log.py` — session heartbeat / unclean-exit report + faulthandler.
- `apps/windows-cc/permissions.py` — doc Levels 1–4 mapped onto R1–R4.
- UI: top-bar EMERGENCY STOP button, halt banner, Safety & STOP page, Resume (type RESUME) dialog.
- `docs/SAFETY.md`, this changelog, `tests/test_phase1_safety.py` (26 tests).

Changed
- `bridge_api.py` — STOP gates on agent_start, shell_confirm, tool_confirm, screen_read, start_workday, wake word; new `halt_status`, `halt_stop`, `halt_resume`, `safety_info`, `start_safety`; `status()` reports `halted`; STOP-trigger settings are file-only.
- `agents/worker.py` — `stop_all()`, `halted` predicate (start/resume refused while STOP is active).
- `agent_tools.py` — shell refuses while stopped; child processes tracked so STOP kills them.
- `video_studio/ffmpeg_tools.py` — encoder process registered with STOP.
- `voice_intents.py` — `halt` and `resume` intents.
- `cc_settings.py` — audit lines are hash-chained; `stop_hotkey` / `stop_file_watch` flags.
- `llm_providers.py` — loads keys from Credential Manager before `api_keys.env`.
- `host_main.py` — session log, faulthandler, starts STOP watcher + hotkey; optional `JARVIS_WEBVIEW_DEBUG=1`.
- `build_exe.ps1` — hidden imports for the new modules.

Not changed: `POLICY.yaml` (user-owned), trading (no live path; typed R4 CONFIRM rule stands), GitHub repo visibility/history.
