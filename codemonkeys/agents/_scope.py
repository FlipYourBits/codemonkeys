"""Shared scope-resolution helper for read-only reviewer agents."""

from __future__ import annotations

from typing import Literal


def build_read_scope_context(
    scope: Literal["file", "diff", "repo"],
    path: str | None,
    file_verb: str = "review",
) -> tuple[str, list[str], str]:
    """Return (method_intro, extra_tools, scope_exclusion) for a read-only reviewer.

    file_verb: the action word used in the file-scope intro ("review" or "audit").
    """
    extra_tools: list[str] = []

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method_intro = f"Read `{path}` and {file_verb} it."
        scope_exclusion = ""
    elif scope == "diff":
        if path:
            method_intro = (
                f"Start by running `git diff main...HEAD -- '{path}'` and reading "
                "the changed files."
            )
        else:
            method_intro = (
                "Start by running `git diff main...HEAD -- '*.py'` and reading the "
                "changed files. If no diff is available, run `git ls-files '*.py'` "
                "and review the most recently changed files."
            )
        scope_exclusion = "\n- Pre-existing issues outside the diff"
        extra_tools.extend(["Bash(git diff*)", "Bash(git ls-files*)"])
    else:
        if path:
            method_intro = f"Review all Python source files under `{path}`."
        else:
            method_intro = (
                "Run `git ls-files '*.py'` to find all Python source files and "
                "review them."
            )
        scope_exclusion = ""
        extra_tools.append("Bash(git ls-files*)")

    return method_intro, extra_tools, scope_exclusion
