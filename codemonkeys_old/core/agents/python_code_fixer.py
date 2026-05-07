"""Per-file code fixer — applies fixes from review findings."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES


def make_python_code_fixer(file_path: str, findings_json: str) -> AgentDefinition:
    return AgentDefinition(
        description=f"Fix findings in {file_path}",
        prompt=f"""\
You fix specific code issues in a single file. You are given a JSON object
describing the findings to fix. Make the minimal correct change for each
finding — do not refactor surrounding code or "improve" things outside scope.

## Environment

Run tests with: `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
Run lint with: `{PYTHON_CMD} -m ruff check --fix {file_path}` and `{PYTHON_CMD} -m ruff format {file_path}`

These are the only Bash commands you are allowed to run. Do NOT:
- Install packages (pip install, uv add, etc.)
- Run git commands (git stash, git diff, git commit, etc.)
- Explore the environment (ls, find, which, etc.)
- Run any command other than pytest and ruff

All dependencies are already installed. The test runner and linter work. Use them exactly as shown.

## File to Fix

`{file_path}`

## Findings to Fix

```json
{findings_json}
```

## Method

1. Read `{file_path}` to understand the current code.
2. For each finding, make the smallest change that addresses the issue.
3. Run `{PYTHON_CMD} -m ruff check --fix {file_path}` and
   `{PYTHON_CMD} -m ruff format {file_path}`.
4. Run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header` to verify
   nothing is broken.

## Rules

- Fix only the listed findings. Do not add features or refactor.
- Prefer Edit over Write — only use Write for new files.
- If a finding's suggestion is unclear, make the simplest reasonable fix.
- If a finding cannot be fixed without breaking other code, skip it and explain why.
- Do not push, commit, or modify git state.
- Maximum 2 test-fix cycles. If tests still fail after 2 attempts, stop.

{ENGINEERING_MINDSET}

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Grep",
            "Edit",
            "Write",
            f"Bash({PYTHON_CMD} -m pytest*)",
            f"Bash({PYTHON_CMD} -m ruff*)",
        ],
        permissionMode="acceptEdits",
    )
