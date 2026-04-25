"""Branch-namer node: generates a git branch name from a task description."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You generate git branch names. "
    "Read the user's task description and reply with ONE branch name on a single "
    "line. No quotes, no markdown, no explanation, no trailing punctuation. "
    "Follow the git guidelines below."
)

_PROMPT_TEMPLATE = (
    "Generate a git branch name for the following task:\n\n{task_description}"
)


def branch_namer_node(
    *,
    name: str = "branch_namer",
    extra_skills: Sequence[str | Path] = (),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = None,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that writes `branch_name` into state.

    Args:
        extra_skills: additional skill refs to append after git-guidelines.
        on_unmatched: passed through to the underlying ClaudeAgentNode.
        model: optional model override.
        **kwargs: forwarded to ClaudeAgentNode (e.g. allowed_tools, allow,
            deny, prompt_template, max_turns).
    """
    skills = ["git-guidelines", *extra_skills]
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        prompt_template=_PROMPT_TEMPLATE,
        output_key="branch_name",
        on_unmatched=on_unmatched,
        model=model,
        max_turns=kwargs.pop("max_turns", 1),
        **kwargs,
    )
