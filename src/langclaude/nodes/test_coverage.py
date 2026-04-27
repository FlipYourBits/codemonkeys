"""Coverage node: Claude agent that runs coverage tools, analyzes gaps,
and optionally writes tests to fill them — all in one session.

When Edit/Write are denied (default), the agent runs coverage and reports
uncovered areas. When allowed, it also writes tests to cover important gaps.
Control interactive approval via on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_READONLY_PROMPT = (
    "You are a senior engineer analyzing test coverage. "
    "Use Bash to run `pytest --cov` (or the project's coverage tool). "
    "Identify uncovered lines and branches. "
    "Do not edit files. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, and recommendation."
)

_READWRITE_PROMPT = (
    "You are a senior engineer analyzing test coverage. "
    "Use Bash to run `pytest --cov` (or the project's coverage tool). "
    "Identify uncovered lines and branches. "
    "Then write tests to cover the most important gaps — focus on "
    "business logic and error paths. Re-run coverage to verify "
    "improvement. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you fixed it."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_coverage_node(
    *,
    name: str = "test_coverage",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "coverage_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a coverage node.

    By default read-only: runs coverage and reports gaps. To enable
    writing tests, pass Edit/Write in the allow list.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key``: findings JSON.
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
    system_prompt = _READWRITE_PROMPT if can_fix else _READONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — analyze coverage only for files changed since "
            "{%s}. Run `pytest --cov` in {working_dir}."
        ) % base_ref_key
    else:
        prompt_template = (
            "FULL mode — analyze coverage for the entire repo at "
            "{working_dir}. Run `pytest --cov`."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
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
