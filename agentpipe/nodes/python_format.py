"""Format Python code with ruff."""

from __future__ import annotations

import sys

from agentpipe.nodes.base import ShellNode, Verbosity


class PythonFormat(ShellNode):
    def __init__(
        self,
        *,
        timeout: float | None = None,
        verbosity: Verbosity = Verbosity.silent,
    ) -> None:
        super().__init__(
            name="python_format",
            command=[sys.executable, "-m", "ruff", "format", "."],
            check=False,
            timeout=timeout,
            verbosity=verbosity,
        )
