"""Pytest node: Claude agent that runs the test suite, analyzes failures,
and optionally fixes them — all in one session.

When Edit/Write are denied (default), the agent runs pytest and reports
findings. When allowed, it also diagnoses and fixes failing tests.
Control interactive approval via on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_READONLY_PROMPT = (
    "You are a senior engineer running the project's test suite. "
    "Use Bash to run pytest (or the project's test runner). "
    "Analyze any failures: read the failing test and the code under test "
    "to identify the root cause. "
    "Do not edit files. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, and recommendation."
)

_READWRITE_PROMPT = (
    "You are a senior engineer running the project's test suite. "
    "Use Bash to run pytest (or the project's test runner). "
    "Analyze any failures: read the failing test and the code under test "
    "to identify the root cause. Then fix the underlying bug — do not "
    "weaken assertions or delete tests. Make the smallest correct change. "
    "Re-run the tests to verify your fix. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you fixed it."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_pytest_node(
    *,
    name: str = "pytest",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "test_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a pytest node.

    By default read-only: runs tests and reports failures. To enable
    fixing, pass Edit/Write in the allow list.

    State input:
        working_dir: repo root.

    State output:
        ``output_key``: findings JSON.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _READWRITE_PROMPT if can_fix else _READONLY_PROMPT

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template="Run the test suite in {working_dir} and analyze any failures.",
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
