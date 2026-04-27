"""Docs-review node: checks documentation for drift against the code.

Owns doc accuracy exclusively: stale docstrings, outdated READMEs,
missing public-API docs, inconsistent terminology. Does NOT check
code quality, security, tests, or formatting — other nodes own those.

Report-only: returns JSON findings without making any edits.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy
from langclaude.skills.docs_review import DOCS_REVIEW

_SYSTEM_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the skill below exactly. "
    "Report findings only — do not fix issues. "
    "Do not run tests, linters, or install packages — only read code and docs. "
    "Output JSON only as your final message."
)

Mode = Literal["diff", "full"]

_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]


def docs_review_node(
    *,
    name: str = "docs_review",
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
            "DIFF mode — report only doc drift introduced by the diff "
            "against {base_ref}. Start by running `git diff {base_ref}...HEAD` and "
            "reading any doc files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        )
    else:
        prompt_template = (
            "FULL mode — review docs in the repository at "
            "{working_dir}. Start by listing files and reading any doc "
            "files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT + DOCS_REVIEW,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
