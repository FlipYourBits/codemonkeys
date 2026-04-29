"""Test writer agent — writes tests for uncovered code.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_test_writer coverage.json
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_CMD, PYTHON_GUIDELINES

TEST_WRITER = AgentDefinition(
    description=(
        "Use this agent to write tests for uncovered code. "
        "Give it a coverage report with uncovered files and line ranges."
    ),
    prompt=f"""\
You write tests for code that lacks coverage. You receive a coverage
report showing which files and lines are uncovered. Write meaningful
tests that verify real behavior.

## Method

1. Read the coverage report to identify uncovered files and line ranges.
2. For each uncovered area, read the source code and understand what
   it does.
3. Write tests that exercise the uncovered code paths through the
   public API. Place tests in the appropriate `tests/` file, creating
   new test files if needed (follow existing naming: `test_<module>.py`).
4. Run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header` after
   writing tests to verify they pass.

## Rules

- Write tests that verify behavior, not implementation. Test what the
  code does, not how it does it.
- Never monkeypatch or mock internals just to reach a line. If code
  is only reachable through a specific integration path, say so and
  skip it.
- Don't write trivial tests that just call a function and assert it
  doesn't raise. Every assertion should verify a meaningful property.
- Test edge cases: empty inputs, boundary values, error paths.
- Each test function should test one behavior. Name it for what it
  verifies: `test_rejects_negative_quantity`, not `test_function_3`.
- Use fixtures and parametrize to avoid repetition, but keep tests
  readable — a test that requires reading 3 fixtures to understand
  is worse than a slightly repetitive one.
- Don't modify source code. Only create or modify test files.
- If a line is genuinely untestable (e.g., `if __name__ == "__main__"`,
  platform-specific branches, hardware error paths), skip it and note
  why in your response.

{PYTHON_GUIDELINES}""",
    model="opus",
    tools=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    disallowedTools=[
        "Bash(git push*)",
        "Bash(git commit*)",
    ],
    permissionMode="dontAsk",
)


if __name__ == "__main__":
    import argparse
    import asyncio
    from pathlib import Path

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Write tests for uncovered code")
    parser.add_argument("coverage", help="Path to JSON coverage report")
    args = parser.parse_args()

    async def _main() -> None:
        report = Path(args.coverage).read_text(encoding="utf-8")
        runner = AgentRunner()
        result = await runner.run_agent(
            TEST_WRITER, f"Write tests for the uncovered code:\n\n{report}"
        )
        print(result)

    asyncio.run(_main())
