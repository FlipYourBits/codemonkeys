"""Generic fixer agent — applies fixes from any structured findings."""

from __future__ import annotations

from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition


class FixItem(BaseModel):
    """Universal finding format — works with any source."""

    file: str | None = None
    line: int | None = None
    severity: str | None = None
    category: str | None = None
    title: str
    description: str
    suggestion: str | None = None


class FixResult(BaseModel):
    """What the fixer did."""

    applied: list[str]
    skipped: list[str]
    summary: str


def make_fixer(
    items: list[FixItem],
    *,
    model: str = "opus",
) -> AgentDefinition:
    """Applies fixes from structured findings to the codebase."""
    findings_text = ""
    for i, item in enumerate(items, 1):
        loc = ""
        if item.file:
            loc = f" in `{item.file}`"
            if item.line:
                loc += f" at line {item.line}"
        sev = f" [{item.severity}]" if item.severity else ""
        suggestion = f"\n   Suggestion: {item.suggestion}" if item.suggestion else ""
        findings_text += (
            f"{i}. **{item.title}**{sev}{loc}\n"
            f"   {item.description}{suggestion}\n\n"
        )

    return AgentDefinition(
        name="fixer",
        model=model,
        system_prompt=f"""\
You are a code fixer. Apply the fixes described below to the codebase.

## Findings to Fix

{findings_text}

## Process

For each finding:
1. Read the relevant file to understand the full context around the issue
2. Apply the fix — use the suggestion as guidance but use your judgment for the best implementation
3. Verify: run `ruff check --fix . && ruff format .` after edits to ensure no lint errors

## Rules

- Only modify what's needed to fix each finding. Do not refactor surrounding code.
- If a finding's suggestion is unclear or would break something, skip it and explain why.
- After all fixes, run `ruff check .` and `pyright .` to verify nothing is broken.
- Report which findings you applied and which you skipped.""",
        tools=["Read", "Edit", "Grep", "Bash"],
        output_schema=FixResult,
    )
