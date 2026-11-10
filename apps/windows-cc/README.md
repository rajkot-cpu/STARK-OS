# JARVIS Command Center (`windows-cc`)

WebView2 HUD shell for STARK OS. Requires Windows WebView2 Evergreen Runtime.

```powershell
cd apps\windows-cc
pip install -r requirements.txt
# also needs apps/windows-panel deps (pyyaml, pyttsx3, …)
$env:JARVIS_HOME = "C:\Users\rajk1\jarvis"
python host_main.py
```

API keys: set `JARVIS_ANTHROPIC_API_KEY`, `JARVIS_OPENAI_API_KEY`, `JARVIS_GEMINI_API_KEY`, `JARVIS_GROQ_API_KEY` (vault/env only — never commit).

## Voice, agents and opt-in features (2026-11-10)

All of these live on the **Settings** page. Opt-ins are OFF by default and every risky action is R3.

| Feature | Default | How it works | Risk |
|---|---|---|---|
| "Hey Jarvis" wake word + barge-in | **Off** — tick *Always listen for Hey Jarvis* (R3 confirm, audited) | openWakeWord `hey_jarvis_v0.1` ONNX on-device; on wake → listen → chat → speak. Saying "Hey Jarvis" or **Stop Speaking** interrupts a reply | R3 opt-in |
| Offline speech-to-text | Auto: offline when the model is on disk | faster-whisper `tiny.en` int8 CPU, numpy input. Model downloads to `<root>\models` on first use (*Download offline model*); Google is used until then | R1 |
| Natural voice | Prabhat (en-IN) | edge-tts (online) → Windows SAPI offline fallback; choose Prabhat, Neerja or Windows voice | R1 |
| MCP tool servers | none | `config/mcp_servers.json` (`{"servers": []}`; see `mcp_servers.example.json`). Tools are offered to agents as `mcp_<server>_<tool>`; **every call** needs *Approve once* on the agent card | R3 per call |
| Web search | on (agents) | `web_search` tool: ddgs (6 s timeout) → Gemini google_search grounding fallback | R1 read-only |
| Screen reading | manual | *Read My Screen (R3)* or an agent's `screen_read` request → confirm → mss capture → 1280 px JPEG in memory → Gemini (OpenAI fallback) describes it. Nothing saved; audited | R3 per capture |

Settings are stored in `config/cc_settings.json` (no secrets). Audit lines go to `logs/audit.jsonl`.

## Commands that start agents (Builder + provider fallback)

- Type in the command bar on Home (or press 🎤 / Tap to Speak / say "Hey Jarvis"):
  - `build me a hello-world page called test-site` → **Builder** starts at once, writes files in `jarvis\workspace\test-site`
  - `research GST rates on medicines` → Research · `browse python.org …` → Browser · `check system health` → System
  - `list my skills` → Task · `remember that …` → Memory · `review the code in apps` → Coding
  - `start <agent> <goal>` / `ask the builder to …` / `stop builder`
  - `start trading` / `stop trading` are reserved for the voice-trading release (no-op here).
  - Anything else goes to chat.
- Agents try Gemini first; on quota (429), server errors, bad key or no network they fall back to
  OpenAI (gpt-4o-mini), then Groq if a key exists. The card shows the AI used and any warning.
- Builder tools: `write_file` (new files, auto + audited), `make_dir`, `ws_list_dir`, `ws_read_file`
  are confined to `workspace\<project>`; overwrite/delete and any code run (`shell`) need R3 approval,
  after which the agent continues automatically.
