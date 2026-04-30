"""Quality review agent — clean code, naming, design patterns, docstrings.

Usage:
    .venv/bin/python -m codemonkeys.agents.python_quality_review
    .venv/bin/python -m codemonkeys.agents.python_quality_review --scope file --path src/main.py
    .venv/bin/python -m codemonkeys.agents.python_quality_review --scope repo
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.prompts import PYTHON_SOURCE_FILTER


def make_python_quality_reviewer(
    scope: Literal["file", "diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    tools: list[str] = ["Read", "Glob", "Grep"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method_intro = f"Read `{path}` and review it."
        scope_exclusion = ""
    elif scope == "diff":
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
        tools.extend(["Bash(git diff*)", "Bash(git ls-files*)"])
    else:
        if path:
            method_intro = f"Review all Python source files under `{path}`."
        else:
            method_intro = (
                "Run `git ls-files '*.py'` to find all Python source files and "
                "review them."
            )
        scope_exclusion = ""
        tools.append("Bash(git ls-files*)")

    return AgentDefinition(
        description=(
            "Use this agent to review Python code for clean code violations: "
            "naming, function design, class design, docstrings, error handling, "
            "Pythonic patterns, dead code, and design pattern issues."
        ),
        prompt=f"""\
You review Python code for clean code violations and maintainability
issues. You check everything that automated tools (linters, formatters,
type checkers) cannot catch — naming quality, function design, class
design, documentation accuracy, and Pythonic patterns.

Report findings only — do not fix issues.

{PYTHON_SOURCE_FILTER}

## Method

{method_intro} Check every category below. Only report when
you're confident a real problem exists — not style preferences.

### `naming`

- Variable/function names that don't describe intent
  (`data`, `result`, `tmp`, `x` outside comprehensions)
- Names that describe type instead of meaning
  (`user_dict` → `users_by_id`, `name_string` → `name`)
- Boolean variables/functions missing is_/has_/can_/should_ prefix
  (`valid` → `is_valid`, `check_auth` → `is_authenticated`)
- Abbreviations that aren't universally understood
  (`cfg` is fine, `usr_mgr` is not)
- Single-letter variables outside comprehensions, lambdas, or
  well-known conventions (i/j for indices, x/y for coordinates)
- Constants not in UPPER_SNAKE_CASE
- Class names not in PascalCase
- Misleading names — function does X but is named Y
- Names that shadow builtins (`list`, `type`, `id`, `input`)

### `function_design`

- Functions longer than ~40 lines — suggest extracting a helper
- Functions with more than 4 parameters — suggest a config
  dataclass or breaking into smaller functions
- Deeply nested conditionals (3+ levels) — suggest early
  returns / guard clauses
- Functions that do more than one thing (fetch + parse + validate
  in one function) — suggest splitting
- Side effects hidden in functions that look like getters or
  pure computations (e.g., `get_user()` that also logs to DB)
- Boolean parameters that change behavior — suggest separate
  functions (`process(data, reverse=True)` → `process` + `process_reversed`)
- Functions that return different types depending on input
  (returns `str` sometimes, `None` sometimes, `list` sometimes)
- Functions with no return type hint on public API
- `*args` / `**kwargs` used as a crutch to avoid defining a proper
  signature

### `class_design`

- God classes — more than ~10 public methods or mixed
  responsibilities (data access + business logic + rendering)
- Classes with only `__init__` and no methods — should be a
  `dataclass`, `NamedTuple`, or plain dict
- Deep inheritance hierarchies (3+ levels) — suggest composition
- Abstract base classes with no abstract methods
- Mutable class attributes shared across all instances when
  per-instance state was intended
- `__eq__` defined without `__hash__` — breaks dict/set behavior
- Classes used as namespaces for static methods — use a module
- Overuse of `@property` for computed values that should be methods

### `documentation`

- Public functions/classes/methods (no leading underscore, in
  `__all__` or visible at package root) missing docstrings
- Docstring that doesn't match the current signature — wrong
  params, missing params, wrong return type, wrong exceptions
- Docstring examples that use renamed or removed APIs
- Docstring that describes behavior the implementation no longer
  exhibits (e.g., "raises ValueError" but the function returns None)
- Module missing a module-level docstring explaining its purpose
- Docstring that restates the function name without adding value
  (`def get_user(): \"\"\"Get the user.\"\"\"`)

### `error_handling`

- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging or re-raising
  (`except SomeError: pass`)
- Missing error path on a fallible operation (file read, network
  call, JSON parse, subprocess)
- Try/except block that's too wide — wraps 20 lines when only
  1 line can raise the caught exception
- Raising generic `Exception` or `ValueError` when a custom
  exception would be clearer
- Error messages that don't include diagnostic context
  (`raise ValueError("invalid")` → `raise ValueError(f"invalid age: {{age}}")`)

### `code_structure`

- Dead code — unreachable branches, unused imports, unused
  functions/variables
- Commented-out code blocks left behind
- Duplicated logic that has drifted between copies (same pattern
  implemented slightly differently in 2+ places)
- Magic numbers/strings without named constants
  (`if retries > 3` → `if retries > MAX_RETRIES`)
- Complex boolean expressions that should be extracted into a
  named variable or function
- Deeply nested data access without intermediate variables
  (`data["users"][0]["address"]["city"]`)
- Long parameter lists passed through multiple call layers
  unchanged — suggest a context/config object

### `pythonic_patterns`

- File/connection/resource opened without a context manager
- Manual loop where a list comprehension, generator expression,
  or `map`/`filter` would be clearer and shorter
- Using `isinstance` checks where polymorphism (method dispatch)
  would eliminate the conditional
- Plain dicts for structured data where a `dataclass`,
  `NamedTuple`, or Pydantic `BaseModel` would add type safety
- Using `os.path` instead of `pathlib.Path`
- Using `.format()` or `%` instead of f-strings
- Using `type(x) == Foo` instead of `isinstance(x, Foo)`
- Not using `enumerate()` when both index and value are needed
- Bare `assert` in production code (use exceptions instead)
- Using mutable default arguments (`def f(x=[])`)
- Late-binding closure in a loop (`lambda: i` captures variable,
  not value)

### `performance` (only flag obvious issues)

- Quadratic loops over data that could be set/dict-indexed
- N+1 database queries in a loop
- Repeated computation inside a loop that could be hoisted out
- Loading entire collection into memory when a generator would do
- String concatenation in a loop instead of `"".join()`
- Re-compiling the same regex on every call

### `api_contract`

- Inconsistent return types across code paths (some paths return
  a value, others return None implicitly)
- Breaking change to a public function/method signature
- Function renamed but old name not deprecated or aliased
- Mutable default argument in a public API

## Triage

- Only report findings you would flag in a real code review. If
  you're not sure, leave it out.
- Drop anything where you can't articulate a concrete problem —
  "I would have written it differently" is not a finding.
- Deduplicate — keep the finding with the strongest evidence.
- Cap at 20 findings. If you have more, keep the highest severity
  and confidence ones.

## Exclusions — DO NOT REPORT

- Formatting, whitespace, or import order (linter owns these)
- Type errors or missing type annotations on internal functions
  (type checker owns these)
- Lint rule violations (linter owns these)
- Missing tests or test failures (test runner owns these)
- Security vulnerabilities (security auditor owns these)
- README or project-level documentation staleness (readme reviewer
  owns these)
- Performance issues with no measurable impact{scope_exclusion}

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category, description, recommendation.""",
        model="opus",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Quality review — clean code, naming, design, docstrings")
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="diff")
    parser.add_argument("--path", help="Narrow scope to this file or folder")
    args = parser.parse_args()

    async def _main() -> None:
        agent = make_python_quality_reviewer(scope=args.scope, path=args.path)
        runner = AgentRunner()
        prompt = f"Review Python source files under {args.path}." if args.path else "Review the code."
        result = await runner.run_agent(agent, prompt)
        print(result)

    asyncio.run(_main())
