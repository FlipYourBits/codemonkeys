"""Coverage analyzer agent — runs pytest with coverage and returns a report.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_coverage
    .venv/bin/python -m codemonkeys.agents.python_coverage --scope file --path src/main.py
    .venv/bin/python -m codemonkeys.agents.python_coverage --scope diff
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD


def make_python_coverage_analyzer(
    scope: Literal["file", "diff", "repo"] = "repo",
    path: str | None = None,
) -> AgentDefinition:
    """Create a coverage analyzer agent that runs pytest --cov."""
    tools: list[str] = [f"Bash({PYTHON_CMD} -m pytest*)", "Read"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method = f"""\
1. Run `{PYTHON_CMD} -m pytest --cov={path} --cov-report=json --cov-report=term -q --no-header`
2. Read the generated `coverage.json` file.
3. Return a summary listing uncovered lines for `{path}`."""
    elif scope == "diff":
        git_filter = f" -- '{path}'" if path else " -- '*.py'"
        method = f"""\
1. Run `git diff --name-only main...HEAD{git_filter}` to get changed source files.
2. If no files changed, say "No changed Python files to analyze." and stop.
3. Run `{PYTHON_CMD} -m pytest --cov --cov-report=json --cov-report=term -q --no-header`
4. Read the generated `coverage.json` file.
5. Return coverage only for the changed files. Ignore all other files."""
        tools.append("Bash(git diff*)")
    else:
        cov_target = f"--cov={path}" if path else "--cov"
        method = f"""\
1. Run `{PYTHON_CMD} -m pytest {cov_target} --cov-report=json --cov-report=term -q --no-header`
2. Read the generated `coverage.json` file.
3. Return a summary listing each file with uncovered lines."""

    return AgentDefinition(
        description=(
            "Use this agent to generate a test coverage report. It runs pytest "
            "with coverage and returns uncovered files and line ranges. "
            "Pair with test_writer to improve coverage."
        ),
        prompt=f"""\
You run pytest with coverage and return a structured coverage report.

## Method

{method}

## Output format

Return the results in this exact format:

### Coverage Summary

**Total coverage**: XX%

### Uncovered Files

For each file below 100% coverage, list:

- **file_path** (XX% covered): lines N-M, X-Y, Z

Only list files with uncovered lines. Sort by coverage percentage
ascending (lowest coverage first).

If all files have 100% coverage, say "Full coverage — no uncovered lines."

## Rules

- Run exactly one pytest command. Do not run tests twice.
- Run each command as a separate Bash call. Do not chain commands
  with &&, ||, |, or ;.
- Do not edit any files.
- Do not interpret or suggest fixes — just report what is uncovered.
- Do not run any commands other than those listed in the method.
- Complete in a single response. No follow-up questions.

## Error handling

- If pytest exits non-zero, return the full output as your response.
- If pytest-cov is not installed, return exactly:
  Error: pytest-cov is not installed. Install it with: pip install pytest-cov
- If no tests exist, return exactly:
  No tests found. Cannot generate coverage report.""",
        model="haiku",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Coverage analyzer — run pytest with coverage")
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="repo")
    parser.add_argument("--path", help="File or folder to analyze")
    args = parser.parse_args()

    async def _main() -> None:
        runner = AgentRunner()
        result = await runner.run_agent(
            make_python_coverage_analyzer(scope=args.scope, path=args.path),
            "Generate a test coverage report.",
        )
        print(result)

    asyncio.run(_main())
