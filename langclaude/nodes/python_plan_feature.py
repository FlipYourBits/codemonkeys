"""Python planning node: interactive conversation to produce an implementation plan.

The agent explores the codebase, proposes a plan, and the user can give
feedback until the plan is approved. Falls back to auto-approve when
stdin isn't a TTY.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy
from langclaude.skills.python import CLEAN_CODE

AskFeedback = Callable[[str], Awaitable[str | None]]
PromptFn = Callable[[str, str | None], str]

_SYSTEM_PROMPT = (
    "You are a senior Python engineer creating an implementation plan. "
    "Explore the codebase first — read relevant files, understand the "
    "architecture, check existing patterns. Then produce a clear, "
    "step-by-step plan for the requested feature. "
    "Include which files to create or modify, what each change does, "
    "and how to verify correctness. Be specific — name functions, "
    "classes, and modules. Keep it concise."
)

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
    "Bash(find *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(python *)",
]


def _default_prompt(text: str, content: str | None = None) -> str:
    if content is not None:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(content, file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
    return input(f"\n{text} ")


async def ask_plan_feedback_via_stdin(
    plan: str,
    prompt_fn: PromptFn | None = None,
) -> str | None:
    if not sys.stdin.isatty():
        return None
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(prompt, "[plan] Approve? (y)es or provide feedback:", plan)
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a


def python_plan_feature_node(
    *,
    name: str = "python_plan_feature",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_feedback: AskFeedback = ask_plan_feedback_via_stdin,
    prompt_fn: PromptFn | None = None,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    if prompt_fn is not None and ask_feedback is ask_plan_feedback_via_stdin:
        from functools import partial
        ask_feedback = partial(ask_plan_feedback_via_stdin, prompt_fn=prompt_fn)

    inner_name = f"{name}_inner"
    planner = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[CLEAN_CODE, *extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template="{_plan_prompt}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        task = state.get("task_description", "")
        initial_prompt = (
            f"Explore the codebase and create an implementation plan "
            f"for the following task:\n\n{task}"
        )

        prompt = initial_prompt
        total_cost = 0.0
        while True:
            result = await planner({**state, "_plan_prompt": prompt})
            plan = result[inner_name]
            total_cost += result.get("last_cost_usd", 0.0)

            feedback = await ask_feedback(plan)
            if feedback is None:
                return {name: plan, "last_cost_usd": total_cost}

            prompt = (
                f"Original task:\n\n{task}\n\n"
                f"Your previous plan:\n\n{plan}\n\n"
                f"User feedback:\n\n{feedback}\n\n"
                f"Revise the plan based on this feedback."
            )

    run.__name__ = name
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
