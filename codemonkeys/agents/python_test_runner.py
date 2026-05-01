"""Test runner agent — runs pytest and returns results.

Usage:
    python -m codemonkeys.agents.python_test_runner
    python -m codemonkeys.agents.python_test_runner --scope file --path tests/test_models.py
    python -m codemonkeys.agents.python_test_runner --scope diff
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD


def make_python_test_runner(
    scope: Literal["file", "diff", "repo"] = "repo",
    path: str | None = None,
) -> AgentDefinition:
    """Create a test runner agent that runs pytest."""
    tools: list[str] = [f"Bash({PYTHON_CMD} -m pytest*)"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method = f"""\
1. Run `{PYTHON_CMD} -m pytest {path} -x -q --tb=short --no-header`
2. Return the full stdout and stderr verbatim."""
    elif scope == "diff":
        git_filter = f" -- '{path}'" if path else " -- 'tests/'"
        method = f"""\
1. Run `git diff --name-only main...HEAD{git_filter}` to get changed test files.
2. If no test files changed, run the full test suite:
   `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header`
3. If test files changed, run pytest on those files:
   `{PYTHON_CMD} -m pytest <files> -x -q --tb=short --no-header`
4. Return the full stdout and stderr verbatim."""
        tools.append("Bash(git diff*)")
    else:
        target = path or ""
        method = f"""\
1. Run `{PYTHON_CMD} -m pytest {target} -x -q --tb=short --no-header`
2. Return the full stdout and stderr verbatim."""

    return AgentDefinition(
        description=(
            "Use this agent to run pytest. It runs the test suite and returns the "
            "output. Give it specific pytest flags in the prompt if needed "
            "(e.g., --cov, --cov-report)."
        ),
        prompt=f"""\
You run pytest and return the results.

## Method

{method}

If the prompt specifies a different pytest command, run that instead.

## Rules

- Return the raw pytest output. Do not interpret or fix failures.
- Run each command as a separate Bash call. Do not chain commands
  with &&, ||, |, or ;.
- Do not edit any files.
- Do not run any commands other than those listed in the method.
- Complete in a single response. No follow-up questions.

## Error handling

- If pytest exits non-zero, return the full output as your response —
  test failures ARE the expected result.
- If pytest is not installed, return exactly:
  Error: pytest is not installed. Install it with: pip install pytest
- If pytest fails to collect (import errors, fixture errors), return
  the full error output verbatim.""",
        model="haiku",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse

    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import TOOL_RESULT_SCHEMA

    parser = argparse.ArgumentParser(description="Run pytest and return results")
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="repo")
    parser.add_argument("--path", help="Test file or folder to run")
    args = parser.parse_args()

    run_cli(make_python_test_runner(scope=args.scope, path=args.path), "Run the test suite.", TOOL_RESULT_SCHEMA)
