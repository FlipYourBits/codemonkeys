"""Ruff presets: ShellNodes that run `ruff check --fix` or `ruff format`.

Ruff is included as a runtime dependency so these nodes work without extra
install. If your downstream project pins ruff differently, pip will
reconcile to a single compatible version.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from langclaude.nodes.base import ShellNode


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


def shell_ruff_fix_node(
    *,
    name: str = "ruff_fix",
    fix: bool = True,
    target: str | Callable[[dict[str, Any]], str] = ".",
    cwd_key: str = "working_dir",
    output_key: str = "ruff_fix_output",
    fail_on_findings: bool = False,
    extra_args: list[str] | None = None,
) -> ShellNode:
    """Run `ruff check` (with --fix by default) to auto-fix lint violations."""
    return ShellNode(
        name=name,
        command=_build_argv("check", fix, list(extra_args or []), target),
        cwd_key=cwd_key,
        output_key=output_key,
        check=fail_on_findings,
    )


def shell_ruff_fmt_node(
    *,
    name: str = "ruff_fmt",
    target: str | Callable[[dict[str, Any]], str] = ".",
    cwd_key: str = "working_dir",
    output_key: str = "ruff_fmt_output",
    extra_args: list[str] | None = None,
) -> ShellNode:
    """Run `ruff format` to reformat code."""
    return ShellNode(
        name=name,
        command=_build_argv("format", False, list(extra_args or []), target),
        cwd_key=cwd_key,
        output_key=output_key,
        check=False,
    )
