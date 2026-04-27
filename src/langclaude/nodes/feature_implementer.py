"""Feature-implementer node: implements a described feature in the working dir."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are an expert software engineer implementing a feature in an existing "
    "repository. Read the relevant code first, propose the smallest change "
    "that satisfies the task, then make the edits. Do not run tests — "
    "that is handled by a separate step. Report what you changed and how "
    "to verify."
)

_DEFAULT_ALLOW: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
)

_DEFAULT_DENY: tuple[str, ...] = (
    "Bash(git push*)",
    "Bash(rm -rf*)",
)


def claude_feature_implementer_node(
    *,
    name: str = "feature_implementer",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] = _DEFAULT_DENY,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "last_result",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that implements `task_description` against `working_dir`."""
    allow_list = list(allow) if allow is not None else list(_DEFAULT_ALLOW)
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=allow_list,
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="Implement the following task:\n\n{task_description}",
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
