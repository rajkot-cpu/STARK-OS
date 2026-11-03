# apps/windows-cc/agents/registry.py
ROLES = [
    {
        "id": "coding",
        "name": "Coding",
        "tools": ["list_dir", "read_file"],
        "prompt": (
            "You are the Coding agent for STARK OS. Stay inside JARVIS_ROOT. "
            "Use list_dir/read_file to inspect code. Never claim you applied a diff."
        ),
    },
    {
        "id": "research",
        "name": "Research",
        "tools": ["web_fetch", "list_dir", "read_file"],
        "prompt": (
            "You are the Research agent. Use web_fetch for public https pages and "
            "summarize honestly. Do not invent sources."
        ),
    },
    {
        "id": "memory",
        "name": "Memory",
        "tools": ["list_dir", "read_file"],
        "prompt": (
            "You are the Memory agent. Inspect memory/ and STATE.md with list_dir/read_file. "
            "Do not write files."
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
        "tools": ["list_dir", "read_file"],
        "prompt": (
            "You are the System agent. Read POLICY.yaml, STATE.md, and host notes. "
            "Summarize health; never start workday yourself."
        ),
    },
]
