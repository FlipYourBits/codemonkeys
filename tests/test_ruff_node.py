from __future__ import annotations

import asyncio
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_lint import PythonLint


def _ruff_available() -> bool:
    return importlib.util.find_spec("ruff") is not None


pytestmark = pytest.mark.skipif(
    not _ruff_available(), reason="ruff package not installed"
)


def test_lint_node_command():
    node = PythonLint()
    argv = node._resolve({})
    assert argv[:5] == [sys.executable, "-m", "ruff", "check", "--fix"]
    assert argv[-1] == "."


def test_format_node_command():
    node = PythonFormat()
    argv = node._resolve({})
    assert argv[:4] == [sys.executable, "-m", "ruff", "format"]
    assert "--fix" not in argv
    assert argv[-1] == "."


def test_lint_node_names():
    assert PythonLint().name == "python_lint"
    assert PythonFormat().name == "python_format"


def test_lint_fixes_unsorted_imports(tmp_path: Path):
    f = tmp_path / "messy.py"
    f.write_text(
        textwrap.dedent("""
        import sys
        import os

        x = 1
        print(os, sys, x)
    """).lstrip()
    )

    # Use the underlying ShellNode with a custom command to test ruff with specific args
    from agentpipe.nodes.base import ShellNode

    node = ShellNode(
        name="lint_test",
        command=[sys.executable, "-m", "ruff", "check", "--fix", "--select", "I", "messy.py"],
        check=False,
    )
    asyncio.run(node({"working_dir": str(tmp_path)}))

    cleaned = f.read_text()
    assert cleaned.index("import os") < cleaned.index("import sys"), (
        f"ruff didn't sort imports:\n{cleaned}"
    )
