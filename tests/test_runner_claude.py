from __future__ import annotations

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.nodes.pytest_node import claude_pytest_node


class TestPytestClaudeNode:
    def test_returns_claude_agent_node(self):
        node = claude_pytest_node()
        assert isinstance(node, ClaudeAgentNode)

    def test_default_is_readonly(self):
        node = claude_pytest_node()
        assert "Edit" in node.deny

    def test_readwrite_when_edit_allowed(self):
        node = claude_pytest_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)"],
        )
        assert "Edit" not in node.deny
