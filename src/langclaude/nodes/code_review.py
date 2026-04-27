"""Code-review node: Claude agent that gathers context and reviews code.

Claude runs linters, diffs, and type-checkers itself via Bash, then
performs semantic review and triage following the code-review skill.

When Edit/Write are in the allow list (and not denied), the agent also
fixes issues it finds. Control interactive vs auto approval via
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
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the code-review skill. "
    "Do not edit files; do not push. "
    "Output JSON only as your final message."
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the code-review skill. "
    "After reviewing, fix each issue you found — make the smallest correct "
    "change per issue, verify by re-reading the file. Do not push. "
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


def claude_code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    run_tests: bool = False,
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "review_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a code-review node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    Control interactive approval via on_unmatched:
        - "allow": auto-approve all tool calls (CI / auto mode)
        - "deny": deny unmatched tools
        - ask_via_stdin: prompt per tool call (interactive mode)

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``review_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(
            _READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY
        )

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

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
        system_prompt=system_prompt,
        skills=["code-review", *extra_skills],
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
