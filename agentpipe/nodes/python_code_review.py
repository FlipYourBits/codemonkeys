"""Semantic code review of Python source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentpipe.models import OPUS_4_6
from agentpipe.nodes.base import ClaudeAgentNode


class CodeReviewFinding(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: bug that will cause incorrect behavior in production. MEDIUM: latent bug under specific conditions, or a clear maintainability issue. LOW: minor concerns worth surfacing but not blocking."
    )
    category: str = Field(examples=["logic_error"])
    source: str = Field(examples=["python_code_review"])
    description: str = Field(examples=["Off-by-one in loop bound."])
    recommendation: str = Field(examples=["Use < instead of <=."])
    confidence: Literal["high", "medium", "low"] = Field(
        description="high: confident this is a real issue. medium: likely real but some ambiguity. low: speculative."
    )


class CodeReviewOutput(BaseModel):
    findings: list[CodeReviewFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}],
    )


_SKILL = """\
# Code review

Semantic code review focused on correctness,
maintainability, and design quality. You review things
that linters, formatters, type-checkers, and test runners
cannot catch — those tools run in separate pipeline nodes.
Do not run them.

Report findings only — do not fix issues.

## Source Code Only

Only analyze Python source files. Skip configuration,
generated files, lock files, documentation, and vendored
dependencies. Files to SKIP: `poetry.lock`, `*.pyc`,
`*.egg-info/`, `__pycache__/`, `.venv/`, `dist/`,
`*.generated.*`, `*.md`, `*.rst`.

## Scope

{scope_section}

## Method

{method_intro} Look for issues in these categories. Only
report when you're confident a real problem exists.

### `logic_error`
- Off-by-one bounds, wrong comparison operator
- Swapped arguments to a function
- Broken control flow — early `return` inside a loop that
  should `continue`, missing `else` branch
- Wrong default value that changes semantics
- Negation errors (`if not x` when `x` is meant)
- Mutable default argument (`def f(x=[])`) — shared across
  calls
- Late-binding closure in a loop (`lambda: i` captures the
  variable, not the value)
- Using `is` / `is not` for value comparison instead of
  `==` / `!=` (or vice versa for singletons)
- `__eq__` defined without `__hash__` — breaks dict/set
  behavior
- Mutable class attribute shared across all instances when
  per-instance state was intended

### `complexity`
- Functions longer than ~50 lines — suggest extracting a
  helper
- Deeply nested conditionals (3+ levels) — suggest early
  returns or extraction
- God classes / modules that do too many unrelated things
- Complex boolean expressions that should be named or
  broken up

### `error_handling`
- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging or re-raising
- Missing error path on a fallible operation (file read,
  network, parse)
- Try/except block that's too wide — masks unrelated errors

### `resource_leak`
- File or connection opened without a context manager
- Subprocess started without ensuring termination
- `asyncio` task created without awaiting or cancelling
- Thread pool / executor not shut down (use `with` or
  explicit `.shutdown()`)

### `concurrency`
- Shared mutable state without synchronization
- Missing `await` on an async call
- Race between check and use (TOCTOU) — but NOT
  security-sensitive TOCTOU (security audit owns those)
- Deadlock potential — locks acquired in different orders

### `performance`
- Quadratic loops over data that could be set-indexed
- N+1 database queries in a loop
- Repeated computation that could be hoisted
- Loading entire collection into memory when a generator
  would do

### `api_contract`
- Breaking change to a public signature with no version
  bump or migration note
- Function renamed but old name not deprecated
- Inconsistent return types across code paths (e.g.,
  returns a value on success but `None` on failure with no
  `Optional` annotation or documented intent)

### `dead_code`
- Code branch that can never execute given the conditions
  before it
- Function/import that became unused after the diff
- Commented-out blocks left behind

### `clarity` (high bar — only flag when clearly wrong)
- Misleading name (function does X but is named Y)
- Magic number where a named constant would prevent a bug
- Duplicated logic that's drifted between copies

## Triage

- Only report findings you would flag in a real code
  review. If you're not sure, leave it out.
- Drop anything where you can't articulate a concrete
  failure mode.
- Deduplicate — keep the finding with the strongest
  evidence.
- Cap at 15 findings. If you have more, keep the highest
  severity and confidence ones.

## Exclusions — DO NOT REPORT

- Formatting / whitespace / import order (formatters own
  these)
- Type errors, missing type annotations (type-checkers
  own these)
- Lint violations (linters own these)
- Missing tests or test failures (test node owns these)
- Security vulnerabilities (security audit owns these)
- Docstring accuracy (docs review owns these)
- Naming preferences without a misleading-name argument
- "I would have written this differently" without a
  correctness argument
- Performance issues with no measurable impact{exclusion_extra}
"""


class PythonCodeReview(ClaudeAgentNode):
    def __init__(
        self,
        *,
        scope: Literal["diff", "full_repo"] = "diff",
        base_ref: str = "main",
        **kwargs,
    ) -> None:
        kwargs.setdefault("model", OPUS_4_6)

        if scope == "diff":
            scope_section = (
                "Diff mode: only review changes between the base ref and\n"
                "`HEAD`. Ignore pre-existing issues outside the diff."
            )
            method_intro = (
                "Run the git diff command from the prompt and read every\nchanged file."
            )
            exclusion_extra = "\n- Pre-existing issues outside the diff"
            prompt = (
                f"Review only changes introduced by the diff against {base_ref}. "
                f"Start by running `git diff {base_ref}...HEAD` and reading the changed files."
            )
        else:
            scope_section = (
                "Full repo: review all Python source files in the\nrepository."
            )
            method_intro = (
                "List all Python source files with `git ls-files '*.py'`\n"
                "and read each one."
            )
            exclusion_extra = ""
            prompt = (
                "Review all Python source files in the repository. "
                "Start by running `git ls-files '*.py'` and reading each file."
            )

        super().__init__(
            name="python_code_review",
            output=CodeReviewOutput,
            system_prompt=_SKILL.format(
                scope_section=scope_section,
                method_intro=method_intro,
                exclusion_extra=exclusion_extra,
            ),
            prompt_template=prompt,
            allow=[
                "Read",
                "Glob",
                "Grep",
                "Bash(git diff*)",
                "Bash(git log*)",
                "Bash(git show*)",
                "Bash(git blame*)",
                "Bash(git status*)",
                "Bash(git ls-files*)",
            ],
            deny=[],
            on_unmatched="deny",
            **kwargs,
        )
