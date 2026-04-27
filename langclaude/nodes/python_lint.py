from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from langclaude.nodes.base import ShellNode, Verbosity


def _build_argv(
    mode: str,
    fix: bool,
    extra: list[str],
    target: str | Callable[[dict[str, Any]], str],
) -> Callable[[dict[str, Any]], list[str]]:
    def build(state: dict[str, Any]) -> list[str]:
        path = target(state) if callable(target) else target
        argv = [sys.executable, "-m", "ruff", mode]
        if mode == "check" and fix:
            argv.append("--fix")
        argv.extend(extra)
        argv.append(path)
        return argv

    return build


def python_lint_node(
    *,
    name: str = "python_lint",
    fix: bool = True,
    target: str | Callable[[dict[str, Any]], str] = ".",
    fail_on_findings: bool = False,
    extra_args: list[str] | None = None,
    verbosity: Verbosity = Verbosity.silent,
) -> ShellNode:
    return ShellNode(
        name=name,
        command=_build_argv("check", fix, list(extra_args or []), target),
        check=fail_on_findings,
        verbosity=verbosity,
    )
