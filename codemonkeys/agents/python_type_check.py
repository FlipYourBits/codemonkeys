"""Type checker agent — runs mypy and reports type errors.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_type_check
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD

TYPE_CHECKER = AgentDefinition(
    description=(
        "Use this agent to run mypy type checking on Python code and report type errors."
    ),
    prompt=f"""\
Run mypy on the Python code and report type errors.
Report findings only — do not fix issues.

## Method

1. Run `{PYTHON_CMD} -m mypy --no-error-summary . 2>&1 || true`
2. Parse each error line (file:line: severity: message [code])
3. For each error, read the surrounding code to understand the root cause
4. Classify: errors are HIGH, warnings/notes are MEDIUM
5. Report with the mypy error code as the category

If mypy is not installed, report that as a single finding with category
`missing_tooling` and severity MEDIUM. Do not attempt to type-check
manually.

If no type errors found, report that clearly.

## Triage

- Skip notes that are just informational (e.g., "See https://...")
- If the same root cause produces multiple errors (e.g., wrong type
  propagates through several functions), report it once at the origin
- Cap at 15 findings — keep the highest severity ones

## Exclusions — DO NOT REPORT

- Code quality or style issues (code review owns these)
- Security vulnerabilities (security audit owns these)
- Test failures (test runner owns these)
- Documentation drift (docs review owns these)
- Lint violations (linter owns these)

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category (mypy error code), description, recommendation.""",
    model="haiku",
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Bash(git push*)", "Bash(git commit*)"],
    permissionMode="dontAsk",
)


if __name__ == "__main__":
    import asyncio

    from codemonkeys.runner import AgentRunner

    async def _main() -> None:
        runner = AgentRunner()
        result = await runner.run_agent(TYPE_CHECKER, "Run type checking and report errors.")
        print(result)

    asyncio.run(_main())
