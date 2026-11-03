# GitHub agent patterns (Jarvis windows-cc)

Pattern port only. We studied two popular open-source agent frameworks and re-implemented a few ideas in our own small code. **We did not vendor, install, or depend on either library.**

## Sources
- [openai/openai-agents-python](https://github.com/openai/openai-agents-python) — roughly ~30k GitHub stars (approximate).
- [huggingface/smolagents](https://github.com/huggingface/smolagents) — roughly ~30k GitHub stars (approximate).

## What we borrowed
- **Agent tool loop**: model proposes a tool call → we execute → feed the result back → repeat until a final answer.
- **Max turns / steps cap**: both frameworks bound the loop (`max_turns` / `max_steps`). We use `MAX_STEPS = 12`.
- **Structured tool schemas / function calling**: tools are declared with JSON-schema parameters rather than parsed from free text.

## Our concrete choices
- **Gemini native `functionDeclarations`** (`agents/worker.py`) instead of prompt-parsed tool calls.
- **`MAX_STEPS = 12`** per agent run.
- **Shell tool behind an allowlist** (`shell_gate.py`); anything outside it returns `needs_r3:` and requires an explicit R3 confirm in the bridge/UI before running.
- **`code_search`** — read-only repo search tool.
- **`memory_note`** — append a note to Jarvis memory.

## What we did NOT do
- No vendoring or pip dependency on openai-agents or smolagents.
- No smolagents `CodeAgent`-style arbitrary Python/code execution.
- No LangGraph or other graph orchestration framework.
