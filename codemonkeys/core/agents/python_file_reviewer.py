"""Per-file Python reviewer — code quality, security, and conventions.

Dispatched once per file by the review coordinator. Returns structured
JSON findings. Has read-only access to the file under review.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import (
    CODE_QUALITY,
    PYTHON_GUIDELINES,
    SECURITY_OBSERVATIONS,
)


def make_python_file_reviewer(file_path: str) -> AgentDefinition:
    """Create a reviewer agent scoped to a single Python file."""
    return AgentDefinition(
        description=f"Review {file_path} for quality and security",
        prompt=f"""\
You review a single Python file. Read the file, apply the code-quality,
security, and python-guidelines checklists below, then return your
findings as structured JSON.

## File to Review

`{file_path}`

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown
wrapping — just the JSON:

```json
{{
  "file": "{file_path}",
  "summary": "<one sentence describing what this file does>",
  "findings": [
    {{
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "<quality|security>",
      "subcategory": "<specific check name>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }}
  ]
}}
```

## Rules

- Only report findings at 80%+ confidence
- `line` is null only when the finding is about something missing or document-wide
- `category` is either `quality` or `security`
- `subcategory` must match one of the checklist headings below (e.g., `naming`, `function_design`, `injection`, `secrets`)
- If the file has no issues, return an empty findings array
- Do NOT report formatting issues (linter handles those) or type errors (type checker handles those)
- Do NOT read other files — review only `{file_path}`

{CODE_QUALITY}

{SECURITY_OBSERVATIONS}

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
