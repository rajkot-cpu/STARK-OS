# Jarvis agent tools — GitHub pattern upgrade

**Date:** 2026-11-04  
**Status:** Approved (Chandan)  
**Target:** Installed Jarvis.exe (`apps/windows-cc`) on main.

## Goals

1. Replace the text-JSON tool protocol with a **native Gemini functionDeclarations** loop inspired by high-star GitHub agent frameworks.
2. Add tools: **`code_search`**, **`memory_note`**, allowlisted **`shell`** (R3 for non-allowlist).
3. Document cited repos in `docs/github-agent-patterns.md` (patterns only — **do not vendor** those libraries).

## Non-goals

- Depend on `openai-agents-python`, `smolagents`, LangGraph, or AutoGen as runtime deps
- JarvisRoom / Jarvis3D reinstall
- Unrestricted shell or agent-driven file writes outside `memory_note`

## Research sources (cite in docs)

| Repo | Stars (approx) | Patterns to port |
|------|----------------|------------------|
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | ~30k | Model → execute function tools → feed results → repeat until final; max turns; tool approval concept |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | ~30k | Small tool registry, explicit tool schemas, bounded steps |

Port **ideas and control flow**, not code copy-paste of their modules.

## Approach

**A — Pattern port** (chosen): evolve `agent_tools.py` + `agents/worker.py` inside `windows-cc`.

## Architecture

```
worker._run
  → Gemini generateContent with tools.functionDeclarations
  → parse functionCall parts
  → AgentTools.call / shell gate
  → append functionResponse
  → loop until text-only final or max_steps (12)
UI Agents card shows steps; R3 modal reused for shell outside allowlist
```

## Tools

### Existing (keep)

`list_dir`, `read_file`, `web_fetch`, `skills_list`, `skill_run` (preview)

### New

| Tool | Behavior | Risk |
|------|----------|------|
| `code_search` | Search text under jarvis root (Python walk or `rg` if on PATH); max hits; path sandbox | R1 |
| `memory_note` | Append timestamped note to `memory/agent_notes.md` (create dir/file if needed) | R2 |
| `shell` | Run command if allowlisted; else return `{ok:false, needs_r3:true, command}` for UI confirm | R2 allowlist / R3 else |

### Shell allowlist (exact prefixes / patterns)

Allowed without R3 (cwd = jarvis root, timeout 30s, no network flags):

- `git status`
- `git log` with only `-n <1-20>` and optional `--oneline`
- `python -m unittest` with path under jarvis root
- Windows: `dir` / `cmd /c dir` scoped; Unix worktree: `ls` / `ls -la` relative paths only

Denied always: pipes to curl/wget, `rm`, `del`, `format`, registry edits, absolute paths outside root, `&&` chaining to non-allowlisted commands.

R3 path: bridge exposes `shell_pending` / `shell_confirm(token)` matching existing R3 UX style (reuse modal copy adapted for shell).

## Loop rules

- Max **12** steps (up from 8)
- `missing_key` → error, no fake work
- On Gemini functionCall: execute all calls in the turn sequentially, then continue
- If model returns only text: treat as final
- Stop flag between steps

## Errors / testing / ship

- Unit tests: allowlist accept/reject; path escape on code_search; memory_note append; functionCall parse fixture
- Manual: Start Research with fetch goal; Start Coding with code_search; shell `git status` auto; shell `echo hi` → R3
- Rebuild Jarvis.exe on chandan via `apps/windows-cc/build_exe.ps1`

## Success criteria

- [ ] Worker uses Gemini functionDeclarations (not JSON-in-text primary path)
- [ ] `code_search`, `memory_note`, allowlisted `shell` work under sandbox
- [ ] Non-allowlisted shell requires R3
- [ ] `docs/github-agent-patterns.md` lists openai-agents-python + smolagents with what we borrowed
- [ ] Jarvis.exe rebuilt on user PC
