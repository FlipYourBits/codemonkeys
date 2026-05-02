"""Linter agent — runs ruff check --fix and ruff format.

Usage:
    python -m codemonkeys.agents.python_linter
    python -m codemonkeys.agents.python_linter --scope file --path src/main.py
    python -m codemonkeys.agents.python_linter --scope diff
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD


def make_python_linter(
    scope: Literal["file", "diff", "repo"] = "repo",
    path: str | None = None,
) -> AgentDefinition:
    """Create a linter agent that runs ruff check --fix and ruff format."""
    tools: list[str] = [f"Bash({PYTHON_CMD} -m ruff*)"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method = f"""\
1. Run `{PYTHON_CMD} -m ruff check --fix {path}`
2. Run `{PYTHON_CMD} -m ruff format {path}`
3. Return the combined output from both commands verbatim."""
    elif scope == "diff":
        git_filter = f" -- '{path}'" if path else " -- '*.py'"
        method = f"""\
1. Run `git diff --name-only main...HEAD{git_filter}` to get changed files.
2. If no files changed, say "No changed Python files to lint." and stop.
3. Run `{PYTHON_CMD} -m ruff check --fix` on each changed file.
4. Run `{PYTHON_CMD} -m ruff format` on each changed file.
5. Return the combined output from all commands verbatim."""
        tools.append("Bash(git diff*)")
    else:
        target = path or "."
        method = f"""\
1. Run `{PYTHON_CMD} -m ruff check --fix {target}`
2. Run `{PYTHON_CMD} -m ruff format {target}`
3. Return the combined output from both commands verbatim."""

    return AgentDefinition(
        description=(
            "Use this agent to lint and format Python code. It runs ruff check --fix "
            "and ruff format, modifying files in place. Returns a summary of what changed."
        ),
        prompt=f"""\
You lint and format Python code using ruff.

## Method

{method}

If neither command made changes, say "No lint or format changes needed."

## Rules

- Run the commands exactly as specified above. Do not skip any.
- Run each command as a separate Bash call. Do not chain commands
  with &&, ||, |, or ;.
- Do not interpret, filter, or summarize the output.
- Do not manually edit any files — ruff handles all changes.
- Do not run any commands other than those listed in the method.
- Complete in a single response. No follow-up questions.

## Error handling

- If a command exits non-zero, return the full stderr/stdout as your
  response. Do not retry or attempt to fix the issue.
- If ruff is not installed, return exactly:
  Error: ruff is not installed. Install it with: pip install ruff""",
        model="haiku",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse

    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import TOOL_RESULT_SCHEMA

    parser = argparse.ArgumentParser(
        description="Lint and format Python code with ruff"
    )
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="repo")
    parser.add_argument("--path", help="File or folder to lint")
    args = parser.parse_args()

    run_cli(
        make_python_linter(scope=args.scope, path=args.path),
        "Lint and format the code.",
        TOOL_RESULT_SCHEMA,
    )
