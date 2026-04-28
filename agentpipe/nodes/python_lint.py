"""Lint Python code with ruff."""

from __future__ import annotations

import sys

from agentpipe.nodes.base import ShellNode, Verbosity


class PythonLint(ShellNode):
    def __init__(
        self,
        *,
        timeout: float | None = None,
        verbosity: Verbosity = Verbosity.silent,
    ) -> None:
        super().__init__(
            name="python_lint",
            command=[sys.executable, "-m", "ruff", "check", "--fix", "."],
            check=False,
            timeout=timeout,
            verbosity=verbosity,
        )
