"""Ruff preset: a ShellNode that runs `ruff check` or `ruff format`.

Ruff is included as a runtime dependency so this node works without extra
install. If your downstream project pins ruff differently, pip will
reconcile to a single compatible version.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, Literal

from langclaude.nodes.base import ShellNode

Mode = Literal["check", "format"]


def ruff_node(
    *,
    name: str = "ruff",
    mode: Mode = "check",
    fix: bool = True,
    target: str | Callable[[dict[str, Any]], str] = ".",
    cwd_key: str = "working_dir",
    output_key: str = "ruff_output",
    fail_on_findings: bool = False,
    extra_args: list[str] | None = None,
) -> ShellNode:
    """Build a ShellNode that runs ruff in the working directory.

    Args:
        mode: "check" runs the linter; "format" runs the formatter.
        fix: in check mode, pass --fix so auto-fixable lints are applied.
            Ignored in format mode.
        target: path passed to ruff. Either a literal string or a callable
            that takes state and returns a string. Defaults to ".".
        cwd_key: state key holding the working directory.
        output_key: state key to write ruff's stdout into.
        fail_on_findings: if True, a non-zero exit (= ruff found issues)
            raises and stops the graph. Default False — typical use is to
            tidy up after a Claude node and keep going.
        extra_args: appended raw to the ruff invocation.
    """
    extra = list(extra_args or [])

    def build_argv(state: dict[str, Any]) -> list[str]:
        path = target(state) if callable(target) else target
        # `python -m ruff` instead of `ruff` so this works regardless of
        # whether the venv is activated / ruff is on PATH.
        argv = [sys.executable, "-m", "ruff", mode]
        if mode == "check" and fix:
            argv.append("--fix")
        argv.extend(extra)
        argv.append(path)
        return argv

    return ShellNode(
        name=name,
        command=build_argv,
        cwd_key=cwd_key,
        output_key=output_key,
        check=fail_on_findings,
    )
