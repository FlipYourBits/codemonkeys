"""Linter agent — runs ruff check --fix and ruff format.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_linter
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD

LINTER = AgentDefinition(
    description=(
        "Use this agent to lint and format Python code. It runs ruff check --fix "
        "and ruff format, modifying files in place. Returns a summary of what changed."
    ),
    prompt=f"""\
You lint and format Python code using ruff.

## Method

1. Run `{PYTHON_CMD} -m ruff check --fix .`
2. Run `{PYTHON_CMD} -m ruff format .`
3. Return the combined output from both commands verbatim.

If neither command made changes, say "No lint or format changes needed."

## Rules

- Run both commands in order. Do not skip either one.
- Do not interpret, filter, or summarize the output.
- Do not manually edit any files — ruff handles all changes.
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
        result = await runner.run_agent(LINTER, "Lint and format the code.")
        print(result)

    asyncio.run(_main())
