"""Pytest node: runs the test suite, analyzes failures, and fixes them.

The agent always attempts to run tests, diagnose, and fix. Permissions
control what actually happens: deny Edit/Write for report-only, allow
for auto-fix, or use ask_via_stdin for interactive approval per edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentpipe.nodes.base import ClaudeAgentNode, Verbosity
from agentpipe.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are a senior engineer running the project's test suite. "
    "Use Bash to run pytest (or the project's test runner). "
    "Analyze any failures: read the failing test and the code under test "
    "to identify the root cause. Fix the underlying bug — do not weaken "
    "assertions or delete tests. Make the smallest correct change. "
    "Re-run the tests to verify your fix. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you fixed it."
)

_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
    "Bash(python -m pytest*)",
    "Bash(python -m unittest*)",
]


def python_test_node(
    *,
    name: str = "python_test",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    **kwargs: Any,
) -> ClaudeAgentNode:
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template="Run the test suite in {working_dir} and analyze any failures.",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
