"""Resolve-findings node: interactive issue fixer.

Receives JSON findings from upstream review nodes via _prior_results,
presents a summary to the user, and fixes selected issues.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are a senior engineer fixing issues found by code review. "
    "You will receive JSON findings from prior review nodes. "
    "Present a numbered summary of all findings to the user, grouped by "
    "severity (HIGH first, then MEDIUM, then LOW). Ask the user which "
    "issues to fix: all, specific numbers, a category, or none. "
    "Then fix the selected issues — make the smallest correct change per "
    "issue, verify by re-reading the file. Run tests after fixing to "
    "ensure no regressions. Do not push. "
    "Output JSON only as your final message — a summary of what was fixed."
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

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
]


def resolve_findings_node(
    *,
    name: str = "resolve_findings",
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
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template="Review the findings above and ask the user which to fix.",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
