"""Code-review node: semantic code quality review.

Focuses on things linters and type-checkers cannot catch: logic errors,
excessive complexity, bad abstractions, resource leaks, concurrency bugs.
Does NOT run linters, formatters, type-checkers, or tests — other nodes
own those concerns.

After each review pass, the user can review findings and give feedback
until satisfied. Falls back to auto-approve when stdin isn't a TTY.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy
from langclaude.skills.code_review import SKILL

AskFeedback = Callable[[str], Awaitable[str | None]]

_SYSTEM_PROMPT = (
    "You are a senior engineer conducting a semantic code review. "
    "Read the code directly — do not run linters, formatters, type-checkers, "
    "or tests (other pipeline nodes handle those). "
    "Follow the skill below. Review the code, then fix each issue — "
    "make the smallest correct change per issue, verify by re-reading the file. "
    "Do not push. Output JSON only as your final message."
)

Mode = Literal["diff", "full"]

_ALLOW = [
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]


async def ask_review_feedback_via_stdin(findings: str) -> str | None:
    if not sys.stdin.isatty():
        return None
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(findings, file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    answer = await asyncio.to_thread(
        input, "\n[code_review] Approve? (y)es or provide feedback: ",
    )
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a


def code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_feedback: AskFeedback = ask_review_feedback_via_stdin,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    inner_name = f"{name}_inner"

    if mode == "diff":
        initial_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        initial_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    reviewer = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM_PROMPT + SKILL,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template="{_review_prompt}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        initial_prompt = initial_template.format(**state)
        prompt = initial_prompt
        total_cost = 0.0

        while True:
            result = await reviewer({**state, "_review_prompt": prompt})
            findings = result[inner_name]
            total_cost += result.get("last_cost_usd", 0.0)

            feedback = await ask_feedback(findings)
            if feedback is None:
                return {name: findings, "last_cost_usd": total_cost}

            prompt = (
                f"Your previous review findings:\n\n{findings}\n\n"
                f"User feedback:\n\n{feedback}\n\n"
                f"Address the feedback — re-review or fix as needed."
            )

    run.__name__ = name
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
