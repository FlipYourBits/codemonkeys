from __future__ import annotations

from codemonkeys.nodes.base import ClaudeAgentNode
from codemonkeys.nodes.python_test import PythonTest


class TestPytestClaudeNode:
    def test_returns_claude_agent_node(self):
        node = PythonTest()
        assert isinstance(node, ClaudeAgentNode)

    def test_default_name(self):
        node = PythonTest()
        assert node.name == "python_test"

    def test_default_allows_pytest_bash(self):
        node = PythonTest()
        assert "Bash(python -m pytest*)" in node.allow

    def test_no_blanket_bash(self):
        node = PythonTest()
        assert "Bash" not in node.allow
