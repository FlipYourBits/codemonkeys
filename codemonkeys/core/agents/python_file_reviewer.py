"""Per-file Python reviewer — code quality, security, and conventions.

Dispatched by the review coordinator in batches of up to 3 files.
Returns structured JSON findings. Has read-only access to the files
under review.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import (
    CODE_QUALITY,
    PYTHON_GUIDELINES,
    SECURITY_OBSERVATIONS,
)


def make_python_file_reviewer(
    files: list[str], *, model: str = "sonnet"
) -> AgentDefinition:
    """Create a reviewer agent for one or more Python files."""
    file_list = "\n".join(f"- `{f}`" for f in files)

    return AgentDefinition(
        description=f"Review {len(files)} file(s) for quality and security",
        prompt=f"""\
You review Python files for code quality and security issues. Read each file
listed below, apply the checklists, then return your findings as structured JSON.

## Files to Review

{file_list}

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping — just
the JSON:

{{
  "results": [
    {{
      "file": "<exact path from the list above>",
      "summary": "<one sentence describing what this file does>",
      "findings": [
        {{
          "file": "<path>",
          "line": <int or null>,
          "severity": "<high|medium|low|info>",
          "category": "<quality|security>",
          "subcategory": "<specific check name>",
          "title": "<short one-line summary>",
          "description": "<what's wrong>",
          "suggestion": "<how to fix it, or null>"
        }}
      ]
    }}
  ]
}}

## Rules

- Review EACH file listed above — read all of them
- Include an entry in "results" for every file, even if it has no issues
- Only report findings at 80%+ confidence
- `line` is null only when the finding is about something missing or file-wide
- `category` is either `quality` or `security`
- `subcategory` must match one of the checklist headings below
- If a file has no issues, include it with an empty findings array
- Do NOT report formatting issues (linter handles those) or type errors (type checker handles those)
- Do NOT read files other than those listed above

{CODE_QUALITY}

{SECURITY_OBSERVATIONS}

{PYTHON_GUIDELINES}""",
        model=model,
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
