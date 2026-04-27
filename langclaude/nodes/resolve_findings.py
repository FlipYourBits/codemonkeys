"""Resolve-findings node: fixes issues from upstream review nodes.

Non-interactive (default): auto-fixes all HIGH+ severity issues.
Interactive: presents findings to the user and asks which to fix.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from langclaude.display import default_prompt as _default_prompt
from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

AskFindings = Callable[[str], Awaitable[str | None]]
PromptFn = Callable[[str, str | None], str]

_SYSTEM_AUTO = (
    "You are a senior engineer fixing issues found by code review. "
    "You will receive JSON findings from prior review nodes. "
    "Fix all issues with HIGH or CRITICAL severity — make the smallest "
    "correct change per issue, verify by re-reading the file. "
    "Run tests after fixing to ensure no regressions. Do not push. "
    "Output JSON only as your final message — a summary of what was fixed "
    "and what was skipped (with reasons)."
)

_SYSTEM_INTERACTIVE = (
    "You are a senior engineer fixing issues found by code review. "
    "You will receive JSON findings from prior review nodes. "
    "Present a numbered summary of all findings to the user, grouped by "
    "severity (CRITICAL/HIGH first, then MEDIUM, then LOW). Ask the user "
    "which issues to fix: all, specific numbers, a severity level, or none. "
    "If the user says none or declines, stop immediately and output a JSON "
    "summary with no fixes applied. Otherwise fix the selected issues — "
    "make the smallest correct change per issue, verify by re-reading "
    "the file. Run tests after fixing to ensure no regressions. Do not push. "
    "Output JSON only as your final message — a summary of what was fixed."
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
    "Bash(python -m pytest*)",
    "Bash(python -m unittest*)",
]

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
]


async def ask_findings_via_stdin(
    summary: str,
    prompt_fn: PromptFn | None = None,
) -> str | None:
    if not sys.stdin.isatty():
        return None
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(
        prompt, "[findings] Fix which issues? (all / numbers / none):", summary
    )
    a = answer.strip().lower()
    if a in ("none", "n", "skip", "exit", "quit", "q"):
        return "none"
    if a in ("", "all", "a", "y", "yes"):
        return None
    return a


def resolve_findings_node(
    *,
    name: str = "resolve_findings",
    interactive: bool = False,
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    ask_findings: AskFindings | None = None,
    prompt_fn: PromptFn | None = None,
    **kwargs: Any,
) -> ClaudeAgentNode:
    if interactive:
        system = _SYSTEM_INTERACTIVE
        prompt_tpl = "Review the findings above and ask the user which to fix."
    else:
        system = _SYSTEM_AUTO
        prompt_tpl = (
            "Review the findings above. Fix all CRITICAL and HIGH severity "
            "issues automatically. Skip MEDIUM and LOW."
        )

    node = ClaudeAgentNode(
        name=name,
        system_prompt=system,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template=prompt_tpl,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
    return node
