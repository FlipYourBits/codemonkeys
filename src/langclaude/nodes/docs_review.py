"""Docs-review node: Claude agent that reviews documentation for drift.

Claude reads doc files (README, CHANGELOG, etc.) and checks them against
the code, following the docs-review skill.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SYSTEM_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the docs-review skill exactly. "
    "Do not edit files; do not push. Output JSON only as your final message."
)

_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_DEFAULT_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)


def claude_docs_review_node(
    *,
    name: str = "docs_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] = _DEFAULT_DENY,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "docs_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a docs-review node.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``docs_findings``): fenced JSON block.
    """
    allow_list = list(allow) if allow is not None else list(_ALLOW)

    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only doc drift introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` and "
            "reading any doc files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        ) % (base_ref_key, base_ref_key)
    else:
        prompt_template = (
            "FULL mode — review docs in the repository at "
            "{working_dir}. Start by listing files and reading any doc "
            "files (README, CHANGELOG, etc.). "
            "Then proceed with the docs-review skill."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=["docs-review", *extra_skills],
        allow=allow_list,
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
