"""Bug-fixer node: diagnoses and fixes a described bug in the working dir."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT_HEAVY
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are an expert Python engineer diagnosing and fixing a bug in an "
    "existing repository. First reproduce the issue if possible, then find "
    "the root cause — not just a symptom. Make the smallest correct fix. "
    "Add or update a regression test that fails before the fix and passes "
    "after. Report your diagnosis, the fix, and how you verified it."
)

_DEFAULT_ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write"]


def bug_fixer_node(
    *,
    name: str = "bug_fixer",
    extra_skills: Sequence[str | Path] = (),
    allowed_tools: Sequence[str] = _DEFAULT_ALLOWED_TOOLS,
    allow: Sequence[str] = ("Bash(python*)", "Bash(pytest*)", "Bash(uv*)"),
    deny: Sequence[str] = ("Bash(git push*)", "Bash(rm -rf*)"),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT_HEAVY,
    max_turns: int | None = 30,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that fixes a bug described in `task_description`."""
    skills = ["python-clean-code", "python-security", *extra_skills]
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        allowed_tools=list(allowed_tools),
        allow=list(allow),
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="Diagnose and fix the following bug:\n\n{task_description}",
        output_key="last_result",
        model=model,
        max_turns=max_turns,
        **kwargs,
    )
