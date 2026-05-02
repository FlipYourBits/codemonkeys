"""Type checker agent — runs mypy and returns errors.

Usage:
    python -m codemonkeys.agents.python_type_checker
    python -m codemonkeys.agents.python_type_checker --scope file --path src/main.py
    python -m codemonkeys.agents.python_type_checker --scope diff
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD


def make_python_type_checker(
    scope: Literal["file", "diff", "repo"] = "repo",
    path: str | None = None,
) -> AgentDefinition:
    """Create a type checker agent that runs mypy."""
    tools: list[str] = [f"Bash({PYTHON_CMD} -m mypy*)"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method = f"""\
1. Run `{PYTHON_CMD} -m mypy --output json {path}`
2. Return the full stdout verbatim."""
    elif scope == "diff":
        git_filter = f" -- '{path}'" if path else " -- '*.py'"
        method = f"""\
1. Run `git diff --name-only main...HEAD{git_filter}` to get changed files.
2. If no files changed, say "No changed Python files to type check." and stop.
3. Run `{PYTHON_CMD} -m mypy --output json` on each changed file.
4. Return the full stdout verbatim."""
        tools.append("Bash(git diff*)")
    else:
        target = path or "."
        method = f"""\
1. Run `{PYTHON_CMD} -m mypy --output json {target}`
2. Return the full stdout verbatim."""

    return AgentDefinition(
        description=(
            "Use this agent to run mypy type checking. It runs mypy and returns "
            "type errors as JSON. Give it no arguments — it checks the entire project."
        ),
        prompt=f"""\
You run mypy type checking and return the results.

## Method

{method}

If mypy exits with no errors, say "No type errors."

## Rules

- Return the raw mypy output. Do not interpret, fix, or filter it.
- Run each command as a separate Bash call. Do not chain commands
  with &&, ||, |, or ;.
- Do not edit any files.
- Do not run any commands other than those listed in the method.
- Complete in a single response. No follow-up questions.

## Error handling

- If mypy exits non-zero with errors, return the full output as your
  response — that IS the expected result.
- If mypy is not installed, return exactly:
  Error: mypy is not installed. Install it with: pip install mypy
- If mypy fails to start (config error, import error), return the
  full error output verbatim.""",
        model="haiku",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse

    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import TOOL_RESULT_SCHEMA

    parser = argparse.ArgumentParser(description="Type check Python code with mypy")
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="repo")
    parser.add_argument("--path", help="File or folder to check")
    args = parser.parse_args()

    run_cli(
        make_python_type_checker(scope=args.scope, path=args.path),
        "Run mypy type checking.",
        TOOL_RESULT_SCHEMA,
    )
