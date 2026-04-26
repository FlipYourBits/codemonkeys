from __future__ import annotations

import asyncio
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from langclaude.nodes.ruff_node import ruff_node


def _ruff_available() -> bool:
    return importlib.util.find_spec("ruff") is not None


pytestmark = pytest.mark.skipif(
    not _ruff_available(), reason="ruff package not installed"
)


def test_ruff_node_builds_check_command():
    node = ruff_node(target="src")
    argv = node.command({"working_dir": "/tmp"})
    assert argv[:5] == [sys.executable, "-m", "ruff", "check", "--fix"]
    assert argv[-1] == "src"


def test_ruff_node_format_mode_omits_fix():
    node = ruff_node(mode="format", target="src")
    argv = node.command({"working_dir": "/tmp"})
    assert argv[:4] == [sys.executable, "-m", "ruff", "format"]
    assert "--fix" not in argv


def test_ruff_node_target_callable():
    node = ruff_node(target=lambda s: s["custom"])
    argv = node.command({"custom": "pkg/"})
    assert argv[-1] == "pkg/"


def test_ruff_node_fixes_unsorted_imports(tmp_path: Path):
    f = tmp_path / "messy.py"
    f.write_text(textwrap.dedent("""
        import sys
        import os

        x = 1
        print(os, sys, x)
    """).lstrip())

    node = ruff_node(target="messy.py", extra_args=["--select", "I"])
    asyncio.run(node({"working_dir": str(tmp_path)}))

    cleaned = f.read_text()
    assert cleaned.index("import os") < cleaned.index("import sys"), (
        f"ruff didn't sort imports:\n{cleaned}"
    )
