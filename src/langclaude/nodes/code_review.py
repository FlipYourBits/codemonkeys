"""Code-review node: semantic code quality review.

Focuses on things linters and type-checkers cannot catch: logic errors,
excessive complexity, bad abstractions, resource leaks, concurrency bugs.
Does NOT run linters, formatters, type-checkers, or tests — other nodes
own those concerns.

When Edit/Write are in the allow list (and not denied), the agent also
fixes issues it finds.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SKILL = """\

# Code review

You are conducting a **semantic** code review focused on correctness, maintainability, and design quality. You review things that linters, formatters, type-checkers, and test runners cannot catch — those tools run in separate nodes. Do not run or re-run them. Confidence floor is 0.85.

## Scope

- **Diff mode**: only review changes between the base ref and `HEAD`. Ignore pre-existing issues outside the diff.
- **Full mode**: review the entire current tree.

## Method

For diff mode, run `git diff BASE_REF...HEAD` and read every changed file. For full mode, walk the tree (use `Glob` + `Read`).

Look for issues in these categories. Only report when you're confident a real problem exists.

### `logic_error`
- Off-by-one bounds, wrong comparison operator (`<=` vs `<`)
- Swapped arguments to a function
- Broken control flow — early `return` inside a loop that should `continue`, missing `else` branch
- Wrong default value that changes semantics
- Negation errors (`if not x` when `x` is meant)

### `complexity`
- Functions longer than ~50 lines — suggest extracting a helper
- Deeply nested conditionals (3+ levels) — suggest early returns or extraction
- God classes / modules that do too many unrelated things
- Complex boolean expressions that should be named or broken up

### `error_handling`
- Bare `except:` or `except Exception:` swallowing real errors
- Catching and discarding without logging or re-raising
- Missing error path on a fallible operation (file read, network, parse)
- `try` block that's too wide — masks unrelated errors

### `resource_leak`
- File/socket/db-connection opened without `with`/`defer`/RAII
- Subprocess started without ensuring termination
- Event listener / handler registered without removal

### `concurrency`
- Shared mutable state without lock/channel/atomic
- `await` missing on a coroutine (Python: returns coroutine instead of value)
- Promise/future not awaited in JS
- Race between check and use (TOCTOU at the application layer)
- Deadlock potential — locks acquired in different orders

### `performance`
- Quadratic loops over data that could be set-indexed
- N+1 database queries in a loop
- Repeated computation that could be hoisted
- Loading entire collection into memory when streaming would do

### `api_contract`
- Breaking change to a public signature with no version bump or migration note
- Docstring contradicts the implementation
- Function renamed but old name not deprecated

### `dead_code`
- Code branch that can never execute given the conditions before it
- Function/import that became unused after the diff
- Commented-out blocks left behind

### `clarity` (high bar — confidence ≥ 0.9)
- Misleading name (function does X but is named Y)
- Magic number where a named constant would prevent a real bug
- Duplicated logic that's drifted between copies (one fixed, the other not)

## Triage

- Apply the **0.85 confidence floor**. Below that, drop.
- Drop anything where you can't articulate a concrete failure mode.
- Deduplicate — keep the finding with the strongest evidence.

## Exclusions — DO NOT REPORT

- Formatting / whitespace / import order (formatters own these)
- Type errors, missing type annotations (type-checkers own these)
- Lint violations (linters own these)
- Missing tests or test failures (test/coverage nodes own these)
- Security vulnerabilities (security audit owns these)
- Naming preferences without a misleading-name argument
- "I would have written this differently" without a correctness argument
- Performance issues with no measurable impact
- Pre-existing issues outside the diff (in diff mode)

## Output

Final reply must be a single fenced JSON block matching this schema and nothing after it:

```json
{
  "mode": "diff" | "full",
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "logic_error",
      "description": "One-sentence statement of the issue.",
      "recommendation": "What to change, concretely.",
      "confidence": 0.92
    }
  ],
  "summary": {
    "files_reviewed": 12,
    "high": 1,
    "medium": 2,
    "low": 0
  }
}
```

Severity guide:
- **HIGH**: bug that will cause incorrect behavior in production
- **MEDIUM**: latent bug under specific conditions, or a clear maintainability issue
- **LOW**: clarity / minor concerns worth surfacing but not blocking

If there are no findings, return the JSON with an empty `findings` array."""

_REVIEW_ONLY_PROMPT = (
    "You are a senior engineer conducting a semantic code review. "
    "Read the code directly — do not run linters, formatters, type-checkers, "
    "or tests (other pipeline nodes handle those). "
    "Follow the skill below. Do not edit files; do not push. "
    "Output JSON only as your final message." + _SKILL
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior engineer conducting a semantic code review. "
    "Read the code directly — do not run linters, formatters, type-checkers, "
    "or tests (other pipeline nodes handle those). "
    "Follow the skill below. After reviewing, fix each issue you found — "
    "make the smallest correct change per issue, verify by re-reading the "
    "file. Do not push. "
    "Output JSON only as your final message." + _SKILL
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "review_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a semantic code-review node.

    Focuses on issues linters/type-checkers/tests cannot catch: logic
    errors, complexity, resource leaks, concurrency, API contracts.

    By default read-only (Edit/Write denied). To enable fixing, pass
    Edit/Write in the allow list.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``review_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(
            _READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY
        )

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` "
            "and reading the changed files."
        ) % (base_ref_key, base_ref_key)
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
