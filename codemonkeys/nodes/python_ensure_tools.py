"""Preflight check — install codemonkeys[python] tools if missing."""

from __future__ import annotations

import sys

from codemonkeys.nodes.base import ShellNode


class PythonEnsureTools(ShellNode):
    def __init__(self) -> None:
        super().__init__(
            name="python_ensure_tools",
            command=[sys.executable, "-m", "pip", "install", "codemonkeys[python]"],
        )
