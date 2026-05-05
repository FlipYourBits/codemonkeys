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
