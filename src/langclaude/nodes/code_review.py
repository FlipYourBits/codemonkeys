"""Code-review node: Claude agent that gathers context and reviews code.

Claude runs linters, diffs, and type-checkers itself via Bash, then
performs semantic review and triage following the code-review skill.

When Edit/Write are in the allow list (and not denied), the agent also
fixes issues it finds. Control interactive vs auto approval via
on_unmatched.
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

You are conducting a code review focused on **correctness, maintainability, and code quality** — not security (a separate audit covers that). Better to miss subjective concerns than flood the report with noise. Confidence floor is 0.85 — higher than the security audit, because reviews are noisier by nature.

## Scope

- **Diff mode**: only review changes between the base ref given in the user prompt and `HEAD`. Ignore pre-existing issues outside the diff.
- **Full mode**: review the entire current tree.

## Phase 1 — Pre-collected context

Linter, type-checker, and test output is already collected by a deterministic shell node and injected into your prompt. Do not re-run these tools. Treat their output as **leads**, not verdicts — confirm by reading the relevant code before reporting.

## Phase 2 — Semantic review

For diff mode, run `git diff BASE_REF...HEAD` and read every changed file. For full mode, walk the tree (use `Glob` + `Read`).

Look for issues in these categories. Each example shows the kind of thing worth flagging — only report when you're confident a real problem exists.

### `logic_error`
- Off-by-one bounds, wrong comparison operator (`<=` vs `<`)
- Swapped arguments to a function (`subtract(b, a)` when caller meant `subtract(a, b)`)
- Broken control flow — early `return` inside a loop that should `continue`, missing `else` branch
- Wrong default value that changes semantics
- Negation errors (`if not x` when `x` is meant)

### `missing_test`
- New public function with no test
- New code branch (if/else, error path) with no test exercising it
- Bug fix without a regression test

### `failing_test` (only when `run_tests=True`)
- Test that fails after the diff applied — likely a regression

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

### `type_safety`
- `Any` (Python) / `any` (TS) leaking into public API
- `# type: ignore` / `@ts-ignore` without a reason and without a narrow scope
- Missing type annotations on a new public function
- Casts that bypass type checking (`cast`, `as unknown as ...`)

### `api_contract`
- Breaking change to a public signature with no version bump or migration note
- Docstring or type contradicts the new implementation
- Function renamed but old name not deprecated

### `dead_code`
- Code branch that can never execute given the conditions before it
- Function/import that became unused after the diff
- Commented-out blocks left behind

### `clarity` (high bar — confidence ≥ 0.9)
- Misleading name (function does X but is named Y)
- Magic number where a named constant would prevent a real bug
- Duplicated logic that's drifted between copies (one fixed, the other not)

## Phase 3 — Triage and dedupe

- Cross-reference linter/type-checker output against your semantic findings. Drop tool findings you can't confirm by reading the code.
- Drop duplicates — same issue from multiple sources. Keep the source with the strongest evidence.
- Apply the **0.85 confidence floor**. Below that, drop. Reviews are noisier than security audits, so the bar is higher.
- Drop anything where you can't articulate a concrete failure mode.

## Exclusions — DO NOT REPORT

- Formatting / whitespace / import order (formatters own these)
- Naming preferences without a misleading-name argument
- "I would have written this differently" without a correctness argument
- Performance issues with no measurable impact
- Style guide violations that don't affect behavior
- Type checker noise that's already silenced with a justified `# type: ignore`
- Pre-existing issues outside the diff (in diff mode)

## Output

Final reply must be a single fenced JSON block matching this schema and nothing after it:

```json
{
  "mode": "diff" | "full",
  "scanners_run": ["ruff", "mypy"],
  "scanners_skipped": ["eslint"],
  "tests_run": false,
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "logic_error",
      "source": "review" | "ruff" | "mypy" | "pyright" | "eslint" | "tsc" | "golangci-lint" | "clippy" | "rubocop" | "pytest" | "npm-test" | "go-test" | "cargo-test",
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
- **HIGH**: bug that will cause incorrect behavior in production, or a failing test
- **MEDIUM**: latent bug under specific conditions, or a clear maintainability/contract issue
- **LOW**: clarity / minor concerns worth surfacing but not blocking

If there are no findings, return the JSON with an empty `findings` array."""

_REVIEW_ONLY_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the skill below. "
    "Do not edit files; do not push. "
    "Output JSON only as your final message." + _SKILL
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the skill below. "
    "After reviewing, fix each issue you found — make the smallest correct "
    "change per issue, verify by re-reading the file. Do not push. "
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
    run_tests: bool = False,
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
    """Build a code-review node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    Control interactive approval via on_unmatched:
        - "allow": auto-approve all tool calls (CI / auto mode)
        - "deny": deny unmatched tools
        - ask_via_stdin: prompt per tool call (interactive mode)

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

    test_instruction = (
        "Also run the project's test suite and include failures in your review. "
        if run_tests
        else "Do not run tests. "
    )

    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` and "
            "any available linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % (base_ref_key, base_ref_key, test_instruction)
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and running any available "
            "linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % test_instruction

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
