"""Code review agent — logic errors, resource leaks, dead code, complexity.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_code_review
    .venv/bin/python -m codemonkeys.agents.python_code_review --scope repo
    .venv/bin/python -m codemonkeys.agents.python_code_review --scope diff --path src/
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_SOURCE_FILTER


def make_code_reviewer(
    scope: Literal["diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    if scope == "diff":
        if path:
            method_intro = (
                f"Start by running `git diff main...HEAD -- '{path}'` and reading "
                "the changed files."
            )
        else:
            method_intro = (
                "Start by running `git diff main...HEAD -- '*.py'` and reading the "
                "changed files. If no diff is available, run `git ls-files '*.py'` "
                "and review the most recently changed files."
            )
        scope_exclusion = "\n- Pre-existing issues outside the diff"
    else:
        if path:
            method_intro = f"Review all Python source files under `{path}`."
        else:
            method_intro = (
                "Run `git ls-files '*.py'` to find all Python source files and "
                "review them."
            )
        scope_exclusion = ""

    return AgentDefinition(
        description=(
            "Use this agent to review Python code for logic errors, resource leaks, "
            "error handling gaps, dead code, and complexity issues."
        ),
        prompt=f"""\
Semantic code review focused on correctness, maintainability, and design
quality. You review things that linters, formatters, type-checkers, and
test runners cannot catch. Do not run those tools.

Report findings only — do not fix issues.

{PYTHON_SOURCE_FILTER}

## Method

{method_intro} Look for issues in these categories. Only
report when you're confident a real problem exists.

### `logic_error`
- Off-by-one bounds, wrong comparison operator
- Swapped arguments to a function
- Broken control flow — early `return` inside a loop that should
  `continue`, missing `else` branch
- Wrong default value that changes semantics
- Negation errors (`if not x` when `x` is meant)
- Mutable default argument (`def f(x=[])`) — shared across calls
- Late-binding closure in a loop (`lambda: i` captures the variable,
  not the value)
- Using `is` / `is not` for value comparison instead of `==` / `!=`
  (or vice versa for singletons)
- `__eq__` defined without `__hash__` — breaks dict/set behavior
- Mutable class attribute shared across all instances when per-instance
  state was intended

### `complexity`
- Functions longer than ~50 lines — suggest extracting a helper
- Deeply nested conditionals (3+ levels) — suggest early returns
- God classes / modules that do too many unrelated things
- Complex boolean expressions that should be named or broken up

### `error_handling`
- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging or re-raising
- Missing error path on a fallible operation (file read, network, parse)
- Try/except block that's too wide — masks unrelated errors

### `resource_leak`
- File or connection opened without a context manager
- Subprocess started without ensuring termination
- `asyncio` task created without awaiting or cancelling
- Thread pool / executor not shut down

### `concurrency`
- Shared mutable state without synchronization
- Missing `await` on an async call
- Race between check and use (TOCTOU) — but NOT security-sensitive
  TOCTOU (security audit owns those)
- Deadlock potential — locks acquired in different orders

### `performance`
- Quadratic loops over data that could be set-indexed
- N+1 database queries in a loop
- Repeated computation that could be hoisted
- Loading entire collection into memory when a generator would do

### `api_contract`
- Breaking change to a public signature with no version bump
- Function renamed but old name not deprecated
- Inconsistent return types across code paths

### `dead_code`
- Code branch that can never execute given the conditions before it
- Function/import that became unused after the diff
- Commented-out blocks left behind

### `clarity` (high bar — only flag when clearly wrong)
- Misleading name (function does X but is named Y)
- Magic number where a named constant would prevent a bug
- Duplicated logic that's drifted between copies

## Triage

- Only report findings you would flag in a real code review. If you're
  not sure, leave it out.
- Drop anything where you can't articulate a concrete failure mode.
- Deduplicate — keep the finding with the strongest evidence.
- Cap at 15 findings. If you have more, keep the highest severity and
  confidence ones.

## Exclusions — DO NOT REPORT

- Formatting / whitespace / import order (formatters own these)
- Type errors, missing type annotations (type-checkers own these)
- Lint violations (linters own these)
- Missing tests or test failures (test runner owns these)
- Security vulnerabilities (security audit owns these)
- Docstring accuracy (docs review owns these)
- Naming preferences without a misleading-name argument
- "I would have written this differently" without a correctness argument
- Performance issues with no measurable impact{scope_exclusion}

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category, description, recommendation.""",
        model="opus",
        tools=["Read", "Glob", "Grep", "Bash"],
        disallowedTools=[
            "Bash(git push*)",
            "Bash(git commit*)",
            "Bash(pip install*)",
            "Bash(pip uninstall*)",
        ],
        permissionMode="dontAsk",
    )


CODE_REVIEWER = make_code_reviewer()


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Code review — logic errors, leaks, dead code")
    parser.add_argument("--scope", choices=["diff", "repo"], default="diff")
    parser.add_argument("--path", help="Narrow scope to this file or folder")
    args = parser.parse_args()

    async def _main() -> None:
        agent = make_code_reviewer(scope=args.scope, path=args.path)
        runner = AgentRunner()
        prompt = f"Review Python source files under {args.path}." if args.path else "Review the code."
        result = await runner.run_agent(agent, prompt)
        print(result)

    asyncio.run(_main())
