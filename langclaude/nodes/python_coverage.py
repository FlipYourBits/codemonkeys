"""Coverage node: runs coverage tools, analyzes gaps, and writes tests.

The agent always attempts to run coverage, analyze gaps, and write tests.
Permissions control what actually happens: deny Edit/Write for report-only,
allow for auto-fix, or use ask_via_stdin for interactive approval per edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SYSTEM_PROMPT = (
    "You are a senior engineer analyzing test coverage. "
    "Use Bash to run `pytest --cov` (or the project's coverage tool). "
    "Identify uncovered lines and branches. Write tests to cover the most "
    "important gaps — focus on business logic and error paths. Re-run "
    "coverage to verify improvement. Do not push. "
    "Do not install packages — use only tools already available. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you fixed it."
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
    "Bash(python -m coverage*)",
]


_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
]


def python_coverage_node(
    *,
    name: str = "python_coverage",
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
            "DIFF mode — analyze coverage only for files changed since "
            "{base_ref}. Run `pytest --cov` in {working_dir}."
        )
    else:
        prompt_template = (
            "FULL mode — analyze coverage for the entire repo at "
            "{working_dir}. Run `pytest --cov`."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
