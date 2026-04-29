"""Test runner agent — runs pytest and returns results.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_test_runner
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD

TEST_RUNNER = AgentDefinition(
    description=(
        "Use this agent to run pytest. It runs the test suite and returns the "
        "output. Give it specific pytest flags in the prompt if needed "
        "(e.g., --cov, --cov-report)."
    ),
    prompt=f"""\
You run pytest and return the results.

## Method

1. Run the pytest command specified in the prompt. If no specific command
   is given, run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`.
2. Return the full stdout and stderr verbatim.

## Rules

- Return the raw pytest output. Do not interpret or fix failures.
- Do not edit any files.
- Do not run any other tools or commands besides the one pytest invocation
  specified in the prompt.""",
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
        result = await runner.run_agent(TEST_RUNNER, "Run the test suite.")
        print(result)

    asyncio.run(_main())
