"""Feature-implementer node: implements a described feature in the working dir."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are an expert software engineer implementing a feature in an existing "
    "repository. Read the relevant code first, propose the smallest change "
    "that satisfies the task, then make the edits. Do not run tests — "
    "that is handled by a separate step. Report what you changed and how "
    "to verify."
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
    "Bash(python *)",
    "Bash(pip *)",
    "Bash(npm *)",
    "Bash(node *)",
    "Bash(cargo *)",
    "Bash(make *)",
    "Bash(ls *)",
    "Bash(find *)",
    "Bash(cat *)",
]


def implement_feature_node(
    *,
    name: str = "implement_feature",
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
        prompt_template="Implement the following task:\n\n{task_description}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
