"""Dependency auditor agent — runs pip-audit and returns vulnerabilities.

Usage:
    python -m codemonkeys.agents.python_dep_auditor
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD


def make_python_dep_auditor() -> AgentDefinition:
    """Create a dependency auditor agent that runs pip-audit."""
    return AgentDefinition(
        description=(
            "Use this agent to audit Python dependencies for known vulnerabilities. "
            "It runs pip-audit and returns the results. No scope parameter — "
            "dependencies are always project-wide."
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
- Do not run any commands other than the one pip-audit command above.
- Complete in a single response. No follow-up questions.

## Error handling

- If pip-audit exits non-zero with vulnerabilities, return the full
  output as your response — that IS the expected result.
- If pip-audit is not installed, return exactly:
  Error: pip-audit is not installed. Install it with: pip install pip-audit
- If pip-audit fails to start, return the full error output verbatim.""",
        model="haiku",
        tools=[f"Bash({PYTHON_CMD} -m pip_audit*)"],
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import asyncio

    from codemonkeys.runner import AgentRunner

    async def _main() -> None:
        runner = AgentRunner()
        result = await runner.run_agent(make_python_dep_auditor(), "Audit dependencies for vulnerabilities.")
        print(result)

    asyncio.run(_main())
