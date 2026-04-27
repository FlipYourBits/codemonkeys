"""Security-audit node: semantic security review via code analysis.

Owns security concerns exclusively: injection, auth, secrets, crypto,
data exposure. Reads the code and traces data flow — no external
scanners required. Does NOT check code quality, run tests, or audit
dependencies — other nodes own those.

Report-only: returns JSON findings without making any edits.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from agentpipe.nodes.base import ClaudeAgentNode, Verbosity
from agentpipe.permissions import UnmatchedPolicy
from agentpipe.skills.security_audit import SECURITY_AUDIT

_SYSTEM_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Read the code directly — trace data flow from inputs to sinks. "
    "Follow the skill below. Report findings only — do not fix issues. "
    "Output JSON only as your final message."
)

Mode = Literal["diff", "full"]

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
]


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
    **kwargs: Any,
) -> ClaudeAgentNode:
    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only vulnerabilities introduced by the "
            "diff against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        prompt_template = (
            "FULL mode — audit the repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT + SECURITY_AUDIT,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
