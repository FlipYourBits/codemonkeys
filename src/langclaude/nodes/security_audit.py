"""Security-audit node: Claude agent that runs scanners and reviews for vulnerabilities.

Claude probes for installed scanners (semgrep, gitleaks, pip-audit,
npm audit, etc.), runs them, then performs semantic security review
and triage following the security-audit skill.

When Edit/Write are in the allow list (and not denied), the agent also
fixes vulnerabilities it finds. Control interactive vs auto approval via
on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_REVIEW_ONLY_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "security-audit skill. Do not edit files; do not push. "
    "Output JSON only as your final message."
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "security-audit skill. After reviewing, fix each vulnerability you "
    "found — make the smallest correct change per issue, verify by "
    "re-reading the file. Do not push. "
    "Output JSON only as your final message."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_security_audit_node(
    *,
    name: str = "security_audit",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "security_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a security-audit node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``security_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only vulnerabilities introduced by the "
            "diff against {%s}. Start by running `git diff {%s}...HEAD` "
            "and any installed security scanners. "
            "Then proceed to semantic review and triage."
        ) % (base_ref_key, base_ref_key)
    else:
        prompt_template = (
            "FULL mode — audit the repository at {working_dir}. "
            "Start by listing files and running any installed security "
            "scanners. Then proceed to semantic review and triage."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=["security-audit", *extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
