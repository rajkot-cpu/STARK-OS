# apps/windows-cc/agents/registry.py
ROLES = [
    {
        "id": "coding",
        "name": "Coding",
        "tools": ["list_dir", "read_file", "code_search", "shell"],
        "prompt": (
            "You are the Coding agent for STARK OS. Stay inside JARVIS_ROOT. "
            "Use list_dir/read_file/code_search to inspect code; shell is allowlisted "
            "(risky commands need operator R3 approval). Never claim you applied a diff."
        ),
    },
    {
        "id": "research",
        "name": "Research",
        "tools": ["web_fetch", "list_dir", "read_file", "code_search"],
        "prompt": (
            "You are the Research agent. Use web_fetch for public https pages and "
            "summarize honestly. Do not invent sources."
        ),
    },
    {
        "id": "memory",
        "name": "Memory",
        "tools": ["list_dir", "read_file", "memory_note"],
        "prompt": (
            "You are the Memory agent. Inspect memory/ and STATE.md with list_dir/read_file. "
            "Only write via memory_note (append-only notes)."
        ),
    },
    {
        "id": "browser",
        "name": "Browser",
        "tools": ["web_fetch"],
        "prompt": (
            "You are the Browser agent. Fetch public http(s) URLs and report what you got."
        ),
    },
    {
        "id": "task",
        "name": "Task",
        "tools": ["skills_list", "skill_run", "list_dir"],
        "prompt": (
            "You are the Task agent. List skills and preview SKILL.md via skill_run. "
            "Do not execute shell."
        ),
    },
    {
        "id": "system",
        "name": "System",
        "tools": ["list_dir", "read_file", "shell"],
        "prompt": (
            "You are the System agent. Read POLICY.yaml, STATE.md, and host notes. "
            "Summarize health; never start workday yourself."
        ),
    },
]
