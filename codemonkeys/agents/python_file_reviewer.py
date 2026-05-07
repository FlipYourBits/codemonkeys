"""Per-file Python reviewer agent."""

from __future__ import annotations

from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition


class Finding(BaseModel):
    file: str
    line: int | None = None
    severity: str
    category: str
    title: str
    description: str
    suggestion: str | None = None


class FileFindings(BaseModel):
    results: list[Finding]


def make_python_file_reviewer(
    files: list[str],
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Reviews Python files for code quality and security issues."""
    file_list = "\n".join(f"- `{f}`" for f in files)

    return AgentDefinition(
        name=f"python_file_reviewer:{','.join(f.split('/')[-1] for f in files)}",
        model=model,
        system_prompt=f"""\
You review Python files for code quality and security issues.

## Files to Review

{file_list}

## Output Format

Return a JSON object with a "results" array containing one Finding per issue found.
Each Finding has: file, line (int or null), severity (high/medium/low/info),
category (quality/security), title, description, suggestion (or null).

## Guardrails

You are a read-only reviewer. Do NOT modify any files.""",
        tools=["Read", "Grep"],
        output_schema=FileFindings,
    )
