from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langclaude.nodes.base import ShellNode
from langclaude.nodes.python_lint import _build_argv


def python_format_node(
    *,
    name: str = "python_format",
    target: str | Callable[[dict[str, Any]], str] = ".",
    extra_args: list[str] | None = None,
) -> ShellNode:
    return ShellNode(
        name=name,
        command=_build_argv("format", False, list(extra_args or []), target),
        check=False,
    )
