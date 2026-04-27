from __future__ import annotations

from agentpipe.nodes.base import ClaudeAgentNode
from agentpipe.nodes.python_test import python_test_node


class TestPytestClaudeNode:
    def test_returns_claude_agent_node(self):
        node = python_test_node()
        assert isinstance(node, ClaudeAgentNode)

    def test_default_allows_edit(self):
        node = python_test_node()
        assert "Edit" in node.allow

    def test_default_allows_pytest_bash(self):
        node = python_test_node()
        assert "Bash(python -m pytest*)" in node.allow

    def test_no_blanket_bash(self):
        node = python_test_node()
        assert "Bash" not in node.allow

    def test_custom_deny_overrides_default(self):
        node = python_test_node(deny=["Edit"])
        assert "Edit" in node.deny
