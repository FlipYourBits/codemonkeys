"""Python dependency-audit node: runs pip-audit and fixes vulnerable packages.

The agent always attempts to audit and upgrade. Permissions control what
actually happens: deny Edit/Write for report-only, allow for auto-fix,
or use ask_via_stdin for interactive approval per edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentpipe.nodes.base import ClaudeAgentNode, Verbosity
from agentpipe.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are auditing Python dependencies for known vulnerabilities. "
    "Use pip-audit to scan for CVEs. If pip-audit is not installed, "
    "check requirements.txt / pyproject.toml manually against known "
    "vulnerability databases. Upgrade affected packages to patched "
    "versions. Do not install packages. Do not run tests. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category (vulnerable_dependency), "
    "source, description, recommendation, confidence, and whether you fixed it."
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
    "Bash(pip-audit*)",
    "Bash(pip list*)",
    "Bash(pip show*)",
]

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
    "Bash(python -m pytest*)",
    "Bash(pytest*)",
]


def python_dependency_audit_node(
    *,
    name: str = "python_dependency_audit",
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
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template="Audit Python dependencies in {working_dir} for known vulnerabilities.",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
