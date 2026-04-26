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
    "that satisfies the task, then make the edits. Run any existing tests "
    "or type checks if available. Report what you changed and how to verify."
)

_DEFAULT_ALLOW: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
)


def claude_feature_implementer_node(
    *,
    name: str = "feature_implementer",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] = _DEFAULT_ALLOW,
    deny: Sequence[str] = ("Bash(git push*)", "Bash(rm -rf*)"),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that implements `task_description` against `working_dir`."""
    skills = [*extra_skills]
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        allow=list(allow),
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="Implement the following task:\n\n{task_description}",
        output_key="last_result",
        model=model,
        max_turns=max_turns,
        **kwargs,
    )


def claude_python_feature_implementer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "python_feature_implementer")
    extra = kwargs.pop("extra_skills", ())
    return claude_feature_implementer_node(
        extra_skills=["python-clean-code", *extra], **kwargs
    )


def claude_javascript_feature_implementer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "javascript_feature_implementer")
    extra = kwargs.pop("extra_skills", ())
    return claude_feature_implementer_node(
        extra_skills=["javascript-clean-code", *extra], **kwargs
    )


def claude_rust_feature_implementer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "rust_feature_implementer")
    extra = kwargs.pop("extra_skills", ())
    return claude_feature_implementer_node(
        extra_skills=["rust-clean-code", *extra], **kwargs
    )
