"""Code-review node: Claude agent that gathers context and reviews code.

Claude runs linters, diffs, and type-checkers itself via Bash, then
performs semantic review and triage following the code-review skill.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SYSTEM_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the code-review skill. "
    "Do not edit files; do not push. "
    "Output JSON only as your final message."
)

_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_DEFAULT_DENY: tuple[str, ...] = (
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


def claude_code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    run_tests: bool = False,
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] = _DEFAULT_DENY,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "review_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a code-review node.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``review_findings``): fenced JSON block.
    """
    allow_list = list(allow) if allow is not None else list(_ALLOW)
    test_instruction = (
        "Also run the project's test suite and include failures in your review. "
        if run_tests
        else "Do not run tests. "
    )

    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` and "
            "any available linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % (base_ref_key, base_ref_key, test_instruction)
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and running any available "
            "linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % test_instruction

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=["code-review", *extra_skills],
        allow=allow_list,
        deny=list(deny),
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
