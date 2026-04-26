"""Bug-fixer node: diagnoses and fixes a described bug in the working dir."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are an expert software engineer diagnosing and fixing a bug in an "
    "existing repository. First reproduce the issue if possible, then find "
    "the root cause — not just a symptom. Make the smallest correct fix. "
    "Add or update a regression test that fails before the fix and passes "
    "after. Report your diagnosis, the fix, and how you verified it."
)

_DEFAULT_ALLOW: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
)


def claude_bug_fixer_node(
    *,
    name: str = "bug_fixer",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] = _DEFAULT_ALLOW,
    deny: Sequence[str] = ("Bash(git push*)", "Bash(rm -rf*)"),
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a node that fixes a bug described in `task_description`."""
    skills = [*extra_skills]
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=skills,
        allow=list(allow),
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template="Diagnose and fix the following bug:\n\n{task_description}",
        output_key="last_result",
        model=model,
        max_turns=max_turns,
        **kwargs,
    )


def claude_python_bug_fixer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "python_bug_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_bug_fixer_node(
        extra_skills=["python-clean-code", *extra], **kwargs
    )


def claude_javascript_bug_fixer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "javascript_bug_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_bug_fixer_node(
        extra_skills=["javascript-clean-code", *extra], **kwargs
    )


def claude_rust_bug_fixer_node(**kwargs: Any) -> ClaudeAgentNode:
    kwargs.setdefault("name", "rust_bug_fixer")
    extra = kwargs.pop("extra_skills", ())
    return claude_bug_fixer_node(
        extra_skills=["rust-clean-code", *extra], **kwargs
    )
