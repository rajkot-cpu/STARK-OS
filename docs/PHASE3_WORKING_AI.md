# Phase 3 — Working AI (v3.1.0, 18 Nov 2026)

## What changed
| Area | Module(s) | Status |
|---|---|---|
| Local AI | `local_llm.py`, `llm_router.py`, `ollama/jarvis-local.Modelfile` | Ollama on 127.0.0.1. Model `jarvis-local` = `qwen2.5:3b` (1.9 GB) with `num_gpu 0` (the GTX 1050's CUDA runner crashes with 0xc0000409, so it runs on the CPU at about 13 tok/s). |
| AI routing | `ai_mode` setting | `hybrid` (default) tries cloud first (Gemini → OpenAI → Groq) and falls back to local/offline. Cheap tasks (headline classification) try local first. Other modes: `local_first` and `cloud_only`. Applies to chat, agents (Ollama's OpenAI-compatible tool calls) and the chain. |
| Local HTTP API | `jarvis_api.py` | See below. |
| Keys & brokers | `keys_manager.py`, Settings → Keys & brokers | Any `JARVIS_*` key goes to Credential Manager. Values are never shown or logged. Sahi and "other broker" key/secret slots. |
| Memory | `memory_db.py` (`data/memory.db`) | SQLite + FTS5. Indexes STATE.md, journal/, memory/, notes/, reports/ and workspace/reports, plus chain reports, notes and the paper trade journal. Memory page has a search box. |
| Task queue | `task_queue.py` (`data/tasks.db`) | Survives restart. Tasks that were running come back `interrupted` and never auto-resume. |
| Orchestrator | `orchestrator.py` | Research (web search + memory) → Analyst → Writer. Each step is a real model call. The report goes to `workspace/reports/` and into memory. STOP cancels it. |
| Trading data | `market_data.py`, `indicators.py`, `trading_engine.py` | Yahoo Finance chart API: keyless, unofficial, about 15 min delayed. NIFTY (^NSEI) and BANKNIFTY (^NSEBANK). Computes RSI, Stochastic, CCI, ADX, Williams %R, Momentum, MACD, EMA/SMA 10–200, 5 pivot sets, ATR, Sharpe with bootstrap CI, p-value, max drawdown, VaR/CVaR, a 20-day Monte Carlo bootstrap, a 3-state Markov regime and an EMA-cross walk-forward. Order-book depth is reported as unavailable. |
| Paper trading | `paper_ledger.py` (`data/paper.db`) | ₹10 lakh virtual, long-only, idempotent `client_order_id`. Fills at the delayed last price. The signal is shown and **you** press Paper BUY/SELL. |
| Live trading | `broker_live.py` | Present, **OFF**, fail-closed. Gates: config-file `live_trading_enabled` (UI/API/agents can't set it), no STOP, in-app only, typed `R4 CONFIRM` per order, adapter + keys. No adapter is implemented, so nothing can reach a broker. |
| Cosmetic | app.js / v3.css | Memory row `12.9/23.9 GB` fits at 1366. Feed time is never cut off (HH:MM). The Voice row shows Wake on / Wake stopped / Tap to talk instead of a blanket "Online". |

## Local HTTP API
- Base: `http://127.0.0.1:8765/v1` (Settings → `api_port`)
- Auth: `Authorization: Bearer <token>`
- Token: Windows Credential Manager → `JARVIS/JARVIS_API_TOKEN` (created at first start; Settings → Local API → Copy token / Rotate)

| Method | Path | Notes |
|---|---|---|
| GET | `/v1` | endpoint list |
| GET | `/v1/status` | works during STOP |
| GET | `/v1/readiness` | |
| POST | `/v1/ask` | `{"text", "local": false}` hybrid router |
| POST | `/v1/chat` | Jarvis persona |
| POST | `/v1/command` | same as the command bar |
| GET | `/v1/agents` | |
| POST | `/v1/agents/{id}/run` / `/stop` | R3 steps wait for in-app approval |
| POST | `/v1/chain` | `{"topic"}` → task id |
| GET | `/v1/tasks`, `/v1/tasks/{id}` | |
| GET | `/v1/memory/search?q=` | |
| POST | `/v1/memory/note` | |
| GET | `/v1/trading/snapshot?symbol=NIFTY&tf=1d` | read-only |
| GET | `/v1/trading/paper` | read-only |
| POST | `/v1/stop` | always allowed |
| POST | `/v1/resume` | always 403; resume only by typing RESUME in the window |

Rules:
- Loopback only, with a Host-header check.
- Browser `Origin` → 403 (no CORS).
- During STOP, everything except status and stop returns 423.
- There are no order endpoints.
- Every call goes to the audit chain (method, path, status).

PowerShell example (the token is never printed):
```powershell
$t = & "C:\Program Files\Python313\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\rajk1\jarvis\apps\windows-cc'); import secrets_store; print(secrets_store.read('JARVIS_API_TOKEN'))"
Invoke-RestMethod http://127.0.0.1:8765/v1/status -Headers @{Authorization = "Bearer $t"}
```

## v7/v8 bundle review (`Jarvis_Complete_Native_System_Windows_v7.zip`, then v8 as source of truth)
No hardcoded secrets found (`.env.example` only).

| File | Verdict | Why |
|---|---|---|
| local_llm_engine.py | **ADAPT** → `local_llm.py` | Loopback Ollama generate/list is sound. Dropped auto `ollama serve` and in-app pull. |
| memory_vault_db.py | **ADAPT** (ideas) → `memory_db.py` | SQLite journal + search kept, now FTS5. Its separate kill switch ("UNLOCK JARVIS KILL SWITCH") was **rejected** because it duplicates halt.py STOP. Its `is_demo` rows were not kept. |
| agent_orchestrator.py | **ADAPT** (pattern) → `task_queue.py` | Crash recovery of RUNNING tasks kept (now `interrupted`, never auto-run). The hardcoded ag1–ag10 "institutional" roster was rejected. |
| trading_terminal_monitor.py | **ADAPT** → `paper_ledger.py` | Idempotent paper sandbox kept. Its live path already fails closed (`BROKER_ADAPTER_NOT_IMPLEMENTED`), the same stance as `broker_live.py`. |
| browser_trading_tab.py | **REJECT** | Hardcoded `REFERENCE_MARKET_PRICES` (NIFTY 24,350 vs real ~25,387) and fabricated headlines. `control_logged_in_tab_and_trade` drives a logged-in broker tab over CDP and injects order fields (unsafe order path). |
| institutional_trading_master_controller.py | **REJECT** | Monte Carlo on a synthetic seeded mean/std (demo numbers). Its live-approval flag defaults False but the logic is untestable. Replaced by real-data stats in `indicators.py`. |
| jarvis_native_host.py | **REJECT** (superseded) | A second HTTP host: per-process token, loopback, origin checks. Its `execute/modify/cancel_order` route goes to the fail-closed terminal stub; PowerShell `-Command` is used for metrics. Our `jarvis_api.py` keeps the good parts (loopback, token, origin refusal) with the token in Credential Manager and STOP gating. |
| pc_operator.py | **REJECT** for now | App allowlist is fine, but there are many `powershell -Command` calls, SendKeys and mouse moves. Jarvis already has R3-gated screen/shell tools. |
| research_upgrade_agent.py | **REJECT** | GitHub-stars "evidence score" heuristic. It copies its own source into backups. Not useful. |
| jarvis_trading_desktop.py | **REJECT** | Tk calculator UI with presets; duplicates the HUD. |
| jarvis_command_center_live.html | **REJECT** | Separate Tailwind UI with a CDP "Chrome trading tab" and a kill-switch unlock phrase. Duplicates v3 HUD. |
| Build/Launch .bat | **REJECT** | Unpinned `pip install … MetaTrader5`. Our `build_exe.ps1` is the build. |
| test_jarvis_safety_suite.py | reference only | 15 tests (v7) / 17 (v8, + api hub). Our `tests/test_phase3.py` covers the adapted code. |

### v8 `api_hub_manager.py` (new in v8 — the "API function")

| Piece | Verdict | Why |
|---|---|---|
| Provider catalog (Gemini, Binance, Kite, Alpaca, Finnhub, Alpha Vantage, custom URL/token) | **adapt** | Added as slots in Settings → Keys & brokers (`keys_manager.SLOTS`), stored only in Credential Manager as `JARVIS/JARVIS_*`. |
| "Test connection" per provider | **adapt** | `provider_tests.py`: fixed read-only GETs (Kite profile, Binance account, Alpaca paper account, Finnhub/Alpha Vantage quote, AI models list). Returns status/latency only. |
| Saving keys to plaintext `.env`, first4…last4 masks | reject | Plaintext secrets on disk; masks leak part of a key. We show only set/not set. |
| `REFERENCE_MARKET_PRICES` fallback labelled as an API feed, hardcoded change %, synthetic SL/TP/spread | reject | Fake data shown as real. Jarvis shows "not connected" instead. |
| `api_place_broker_order` (real Kite `POST /orders/regular`, Alpaca, webhook) gated only by kill switch + R:R ≥ 2 | reject | Live orders with no human confirmation. Brokers kite/alpaca/binance are listed in `broker_live.BROKERS` with no adapter (fail-closed, typed R4 CONFIRM required). |
| Free-form custom REST tester (any URL, GET/POST) | reject | SSRF-style risk from the UI/HTTP. Custom URL/token can be stored, not called. |
| Gemini key in the URL query | reject | Keys leak into logs/proxies; we send it in the `x-goog-api-key` header. |
| `/api/api_hub` HTTP routes for saving keys / placing orders | reject | Our local API cannot set keys or place orders; keys are set in-app only. |

**Overlap with the PC's untracked `apps/windows-cc/upgrade_core/` (15 Nov, left untouched):**
- It has its own `local_models`, `memory` (SQLite), `tasking` (SQLite queue), `orchestration` (planner only) and `paper_trading`.
- None of it is wired into the app. The Phase 3 modules above supersede those parts.
- It also holds business/costs/documents/backups/services modules that Phase 3 does not cover.
- Decide later whether to keep or delete it. It still causes the pre-existing `test_upgrade_core` failure on the PC.
