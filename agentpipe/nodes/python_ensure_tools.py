"""Preflight check — install agentpipe[python] tools if missing."""

from __future__ import annotations

import sys

from agentpipe.nodes.base import ShellNode


class PythonEnsureTools(ShellNode):
    def __init__(self) -> None:
        super().__init__(
            name="python_ensure_tools",
            command=[sys.executable, "-m", "pip", "install", "agentpipe[python]"],
        )
