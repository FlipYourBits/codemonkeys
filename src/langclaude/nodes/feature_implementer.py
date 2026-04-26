"""Feature-implementer node: implements a described feature in the working dir."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT_HEAVY
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are an expert Python engineer implementing a feature in an existing "
    "repository. Read the relevant code first, propose the smallest change "
    "that satisfies the task, then make the edits. Run any existing tests "
    "or type checks if available. Report what you changed and how to verify."
)

_DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write"]


def feature_implementer_node(
    *,
    name: str = "feature_implementer",
    extra_skills: Sequence[str | Path] = (),
    allowed_tools: Sequence[str] = _DEFAULT_ALLOWED_TOOLS,
    allow: Sequence[str] = ("Bash(python*)", "Bash(pytest*)", "Bash(uv*)"),
    deny: Sequence[str] = ("Bash(git push*)", "Bash(rm -rf*)"),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT_HEAVY,
    max_turns: int | None = 30,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that implements `task_description` against `working_dir`.

    Defaults pre-allow Read/Glob/Grep/Edit/Write, plus python/pytest/uv shell
    invocations. Pushes and recursive deletes are denied. Anything else
    falls through to `on_unmatched` (default "deny").
    """
    skills = ["python-clean-code", "python-security", *extra_skills]
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        allowed_tools=list(allowed_tools),
        allow=list(allow),
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="Implement the following task:\n\n{task_description}",
        output_key="last_result",
        model=model,
        max_turns=max_turns,
        **kwargs,
    )
