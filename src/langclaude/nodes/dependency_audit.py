"""Dependency-audit node: runs SCA tools and fixes vulnerable dependencies.

The agent always attempts to audit and upgrade. Permissions control what
actually happens: deny Edit/Write for report-only, allow for auto-fix,
or use ask_via_stdin for interactive approval per edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are auditing project dependencies for known vulnerabilities. "
    "Use Bash to run whichever SCA tools are installed: pip-audit, "
    "npm audit, govulncheck, cargo audit, bundler-audit. "
    "Only run tools that are installed and relevant to the project's "
    "ecosystem. After identifying vulnerabilities, upgrade affected "
    "dependencies to patched versions. Verify the upgrade doesn't break "
    "tests. Do not push. Output JSON only as your final message — a list "
    "of findings with file, line, severity, category (vulnerable_dependency), "
    "source, description, recommendation, confidence, and whether you fixed it."
)

_ALLOW = [
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
    "Bash(pip-audit*)",
    "Bash(pip list*)",
    "Bash(pip show*)",
    "Bash(npm audit*)",
    "Bash(npm ls*)",
    "Bash(govulncheck*)",
    "Bash(cargo audit*)",
    "Bash(bundler-audit*)",
]


def dependency_audit_node(
    *,
    name: str = "dependency_audit",
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
        prompt_template="Audit dependencies in {working_dir} for known vulnerabilities.",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
