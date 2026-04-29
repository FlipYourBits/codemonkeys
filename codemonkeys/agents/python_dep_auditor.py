"""Dependency auditor agent — runs pip-audit and returns vulnerabilities.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_dep_auditor
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD

DEP_AUDITOR = AgentDefinition(
    description=(
        "Use this agent to audit Python dependencies for known vulnerabilities. "
        "It runs pip-audit and returns the results."
    ),
    prompt=f"""\
You audit Python dependencies for known vulnerabilities using pip-audit.

## Method

1. Run `{PYTHON_CMD} -m pip_audit --format json --strict --desc`
2. Return the full output verbatim.

If pip-audit exits with no vulnerabilities, say "No known vulnerabilities found."

## Rules

- Return the raw pip-audit output. Do not interpret, fix, or filter it.
- Do not edit any files.
- Do not run any other tools or commands.""",
    model="haiku",
    tools=["Bash"],
    disallowedTools=[
        "Bash(git push*)",
        "Bash(git commit*)",
        "Bash(pip install*)",
        "Bash(pip uninstall*)",
    ],
    permissionMode="dontAsk",
)


if __name__ == "__main__":
    import asyncio

    from codemonkeys.runner import AgentRunner

    async def _main() -> None:
        runner = AgentRunner()
        result = await runner.run_agent(DEP_AUDITOR, "Audit dependencies for vulnerabilities.")
        print(result)

    asyncio.run(_main())
