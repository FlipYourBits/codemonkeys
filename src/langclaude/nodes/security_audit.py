"""Security-audit node: semantic security review via code analysis.

Owns security concerns exclusively: injection, auth, secrets, crypto,
data exposure. Reads the code and traces data flow — no external
scanners required. Does NOT check code quality, run tests, or audit
dependencies — other nodes own those.

After each audit pass, the user can review findings and give feedback
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
from langclaude.skills.security_audit import SKILL

AskFeedback = Callable[[str], Awaitable[str | None]]

_SYSTEM_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Read the code directly — trace data flow from inputs to sinks. "
    "Follow the skill below. Review the code, then fix each vulnerability — "
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


async def ask_audit_feedback_via_stdin(findings: str) -> str | None:
    if not sys.stdin.isatty():
        return None
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(findings, file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    answer = await asyncio.to_thread(
        input, "\n[security_audit] Approve? (y)es or provide feedback: ",
    )
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a


def security_audit_node(
    *,
    name: str = "security_audit",
    mode: Mode = "diff",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_feedback: AskFeedback = ask_audit_feedback_via_stdin,
    **kwargs: Any,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    inner_name = f"{name}_inner"

    if mode == "diff":
        initial_template = (
            "DIFF mode — report only vulnerabilities introduced by the "
            "diff against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        initial_template = (
            "FULL mode — audit the repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    auditor = ClaudeAgentNode(
        name=inner_name,
        system_prompt=_SYSTEM_PROMPT + SKILL,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template="{_audit_prompt}",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        initial_prompt = initial_template.format(**state)
        prompt = initial_prompt
        total_cost = 0.0

        while True:
            result = await auditor({**state, "_audit_prompt": prompt})
            findings = result[inner_name]
            total_cost += result.get("last_cost_usd", 0.0)

            feedback = await ask_feedback(findings)
            if feedback is None:
                return {name: findings, "last_cost_usd": total_cost}

            prompt = (
                f"Your previous audit findings:\n\n{findings}\n\n"
                f"User feedback:\n\n{feedback}\n\n"
                f"Address the feedback — re-audit or fix as needed."
            )

    run.__name__ = name
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
