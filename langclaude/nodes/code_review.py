"""Code-review node: semantic code quality review.

Focuses on things linters and type-checkers cannot catch: logic errors,
excessive complexity, bad abstractions, resource leaks, concurrency bugs.
Does NOT run linters, formatters, type-checkers, or tests — other nodes
own those concerns.

Report-only: returns JSON findings without making any edits.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy
from langclaude.skills.code_review import SKILL

_SYSTEM_PROMPT = (
    "You are a senior engineer conducting a semantic code review. "
    "Read the code directly — do not run linters, formatters, type-checkers, "
    "or tests (other pipeline nodes handle those). "
    "Follow the skill below. Report findings only — do not fix issues. "
    "Output JSON only as your final message."
)

Mode = Literal["diff", "full"]

_ALLOW = [
    "Read", "Glob", "Grep",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]


def code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    **kwargs: Any,
) -> ClaudeAgentNode:
    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT + SKILL,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
