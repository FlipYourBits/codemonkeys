"""Type checker agent — runs mypy and returns errors.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_type_checker
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD

TYPE_CHECKER = AgentDefinition(
    description=(
        "Use this agent to run mypy type checking. It runs mypy and returns "
        "type errors as JSON. Give it no arguments — it checks the entire project."
    ),
    prompt=f"""\
You run mypy type checking and return the results.

## Method

1. Run `{PYTHON_CMD} -m mypy --output json .`
2. Return the full stdout verbatim.

If mypy exits with no errors, say "No type errors."

## Rules

- Return the raw mypy output. Do not interpret, fix, or filter it.
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
        result = await runner.run_agent(TYPE_CHECKER, "Run mypy type checking.")
        print(result)

    asyncio.run(_main())
