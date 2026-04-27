"""Python feature-implementer node: implements a feature following Python guidelines.

After each implementation pass, the user can review and give feedback
until the result is approved. Falls back to auto-approve when stdin
isn't a TTY.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy
from langclaude.skills.python import CLEAN_CODE, SECURITY

AskFeedback = Callable[[str], Awaitable[str | None]]

_SYSTEM_PROMPT = (
    "You are an expert Python engineer implementing a feature in an existing "
    "repository. Read the relevant code first, propose the smallest change "
    "that satisfies the task, then make the edits. Do not run tests — "
    "that is handled by a separate step. Report what you changed and how "
    "to verify."
)

_ALLOW = [
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
    "Bash(python *)",
    "Bash(pip *)",
    "Bash(ls *)",
    "Bash(find *)",
    "Bash(cat *)",
]


async def ask_impl_feedback_via_stdin(summary: str) -> str | None:
    if not sys.stdin.isatty():
        return None
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(summary, file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    answer = await asyncio.to_thread(
        input, "\n[implement] Approve? (y)es or describe what to fix: ",
    )
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a


def python_implement_feature_node(
    *,
    name: str = "python_implement_feature",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_feedback: AskFeedback = ask_impl_feedback_via_stdin,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    inner_name = f"{name}_inner"
    implementer = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[CLEAN_CODE, SECURITY, *extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template="{_impl_prompt}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        task = state.get("task_description", "")
        plan = state.get("python_plan_feature", "")

        if plan:
            initial_prompt = (
                f"Implement the following plan:\n\n{plan}\n\n"
                f"Original task:\n\n{task}"
            )
        else:
            initial_prompt = f"Implement the following task:\n\n{task}"

        prompt = initial_prompt
        total_cost = 0.0
        while True:
            result = await implementer({**state, "_impl_prompt": prompt})
            summary = result[inner_name]
            total_cost += result.get("last_cost_usd", 0.0)

            feedback = await ask_feedback(summary)
            if feedback is None:
                return {name: summary, "last_cost_usd": total_cost}

            prompt = (
                f"Original task:\n\n{task}\n\n"
                f"You've already made changes. The user reviewed your work "
                f"and has this feedback:\n\n{feedback}\n\n"
                f"Fix the issues described above."
            )

    run.__name__ = name
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
