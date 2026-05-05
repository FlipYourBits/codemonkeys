"""CLI entry point — sandbox the process and launch the TUI."""

from __future__ import annotations

from pathlib import Path

from codemonkeys.core.sandbox import restrict
from codemonkeys.tui.app import CodemonkeysApp


def main() -> None:
    cwd = Path.cwd()
    restrict(cwd)
    app = CodemonkeysApp(cwd=cwd)
    app.run()


if __name__ == "__main__":
    main()
