"""Fixer agent — applies targeted fixes for findings from review agents.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_fixer findings.json
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD, PYTHON_GUIDELINES

FIXER = AgentDefinition(
    description=(
        "Use this agent to fix specific code issues identified by review agents. "
        "Give it a list of findings with file, line, and description."
    ),
    prompt=f"""\
You fix specific findings reported by upstream review agents. Each
finding includes a file, line, severity, category, and description.
Fix only what is listed — nothing else.

## Method

1. Read the finding's file and surrounding context.
2. Understand the root cause described in the finding.
3. Make the smallest correct change that resolves the issue.
4. Re-read the changed file to verify correctness.
5. After all fixes, run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
   to check for regressions.

## Rules

- One fix per finding. Do not refactor, clean up, or improve
  surrounding code.
- If a finding is a false positive (the code is actually correct), skip
  it and note why.
- Do not introduce new imports, abstractions, or helpers unless the fix
  requires it.
- Do not push, commit, or modify git state.
- Do not fix issues that are not in the findings list.

{PYTHON_GUIDELINES}""",
    model="opus",
    tools=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    disallowedTools=[
        "Bash(git push*)",
        "Bash(git commit*)",
        "Bash(pip install*)",
        "Bash(pip uninstall*)",
    ],
    permissionMode="dontAsk",
)


if __name__ == "__main__":
    import argparse
    import asyncio
    from pathlib import Path

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Fix findings from review agents")
    parser.add_argument("findings", help="Path to JSON file containing findings")
    args = parser.parse_args()

    async def _main() -> None:
        findings = Path(args.findings).read_text(encoding="utf-8")
        runner = AgentRunner()
        result = await runner.run_agent(FIXER, f"Fix these findings:\n\n{findings}")
        print(result)

    asyncio.run(_main())
