from __future__ import annotations

import asyncio
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from langclaude.nodes.ruff import shell_ruff_fix_node, shell_ruff_fmt_node


def _ruff_available() -> bool:
    return importlib.util.find_spec("ruff") is not None


pytestmark = pytest.mark.skipif(
    not _ruff_available(), reason="ruff package not installed"
)


def test_ruff_fix_builds_check_command():
    node = shell_ruff_fix_node(target="src")
    argv = node.command({"working_dir": "/tmp"})
    assert argv[:5] == [sys.executable, "-m", "ruff", "check", "--fix"]
    assert argv[-1] == "src"


def test_ruff_fmt_builds_format_command():
    node = shell_ruff_fmt_node(target="src")
    argv = node.command({"working_dir": "/tmp"})
    assert argv[:4] == [sys.executable, "-m", "ruff", "format"]
    assert "--fix" not in argv


def test_ruff_fix_target_callable():
    node = shell_ruff_fix_node(target=lambda s: s["custom"])
    argv = node.command({"custom": "pkg/"})
    assert argv[-1] == "pkg/"


def test_ruff_fix_fixes_unsorted_imports(tmp_path: Path):
    f = tmp_path / "messy.py"
    f.write_text(
        textwrap.dedent("""
        import sys
        import os

        x = 1
        print(os, sys, x)
    """).lstrip()
    )

    node = shell_ruff_fix_node(target="messy.py", extra_args=["--select", "I"])
    asyncio.run(node({"working_dir": str(tmp_path)}))

    cleaned = f.read_text()
    assert cleaned.index("import os") < cleaned.index("import sys"), (
        f"ruff didn't sort imports:\n{cleaned}"
    )
