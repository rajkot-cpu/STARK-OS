# Changelog

## v3.2.0 — 2026-11-18 — Phase 3c: Browser tab
- Browser tab + Browser agent tools driving Edge with a persistent `browser-profile` (live view, tabs, address bar, Ask Jarvis about this page).
- Safety: no password/OTP/card typing, R3 for submit/buy/send/post clicks, banking/broker/patient domains blocked, STOP blocks automation, no cookie access.

## v3.1.1 — 2026-11-18 — Phase 3b: search fallback chain
- Web search fallback chain: keyed Tavily/Brave/Serper/SerpAPI (optional) → ddgs → Bing RSS → Google News RSS → DuckDuckGo HTML → Wikipedia → Gemini grounding; retries, per-source timeouts, dedupe, real URLs only.
- Chain reports cite sources with engine names; Tasks page shows sources/engines/citations and a report viewer.
- LLM router: HTTP 429 cools a provider down for 120 s (Gemini → Groq/Ollama fallthrough).

## v3.1.0 — 2026-11-18 — Phase 3: working AI
- Keys & brokers: added Finnhub, Alpha Vantage, Zerodha Kite, Alpaca (paper), Binance slots with read-only **Test** checks (idea from v8 api_hub_manager; keys only in Credential Manager, no orders).
- Local AI: Ollama `jarvis-local` (qwen2.5:3b, CPU) in a hybrid router (cloud first, local fallback/offline; cheap tasks local first) for chat, agents and chains.
- Local HTTP API on 127.0.0.1:8765 (token in Credential Manager `JARVIS/JARVIS_API_TOKEN`, blocked during STOP, no resume/order endpoints).
- Settings: Keys & brokers (any JARVIS_* key, Sahi/other broker slots → Credential Manager), Local AI routing + test, Local API panel.
- Memory DB with full-text search; persistent task queue; Research → Analyst → Writer chain writing real reports.
- Trading: real NIFTY/BANKNIFTY indicators, pivots, statistics, Markov regime, walk-forward from keyless delayed Yahoo data; paper ledger with signal → you press Buy; live adapter slot OFF and fail-closed (typed R4 CONFIRM).
- Fixes: memory row at 1366 px, feed time cut-off, Voice row reflects the wake-word state.
- See docs/PHASE3_WORKING_AI.md (includes the v7 bundle review).

## 2026-11-18 — v3.0.0 Command Center restyle (branch `ui-v3-restyle`)
Reference-mockup restyle (deep navy, neon glass panels). Real data or an honest "not connected" state only.
Previous exe kept as `apps\Jarvis.exe.bak-20261118-prephase2`.

Added
- `ui/css/v3.css`, `ui/js/v3.js` — new top bar (reactor logo, tagline, status pill, big clock, search Ctrl+K, bell = approvals/errors, operator chip, EMERGENCY STOP kept), icon nav, voice card (waveform, mic orb, Focus Mode), AI Core Overview rows, rich Live Intelligence Feed, 2x3 Active Agents, Mission Timeline (today's audit events), Quick Commands grid, ring gauges + CPU sparkline + uptime, Memory Insights, LLM Status (incl. local Ollama), Manage Providers, footer tiles + Talk pill + Executive Briefing.
- Agents page: neon network diagram (input layer → central LLM adapter → 8 agents with distinct colours/shapes, animated flows, real states) and a Data Sources layer (web search, memory, files, MCP, market data = not connected).
- Memory page: brain map linked to real recent files and source folders, Neural Processes / System Analytics / sources ring.
- Security page: AI Shield bound to the audit chain, STOP state, Credential Manager and R1–R4 policy.
- Trading page (PAPER — no live orders): statistical validation, technical analysis, order book, news sentiment, portfolio risk and Markov regime layouts with "connect a data source" empty states. No order calls exist.
- `ui_sources.py` (Ollama detection, data sources), bridge `local_ai`, `sources`, `app_info`; `metrics.snapshot` adds RAM GB, network rate, Jarvis uptime; `memory_index.build` adds per-source counts, bytes, recent files.
- Hero core: thin lat-long wireframe globe, holographic pedestal rings, caption and greeting bubble.

Changed
- Nav icons are flat SVG (the per-button WebGL icons used one WebGL context each; with the new pages that reached Chromium's 16-context limit). WebGL is now only the hero core and the agent orbit.
- `open_folder` accepts a path relative to the Jarvis folder (Quick Command "Open Workspace").

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
