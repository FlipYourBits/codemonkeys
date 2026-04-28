from __future__ import annotations

from agentpipe.nodes.base import ClaudeAgentNode
from agentpipe.nodes.python_code_review import PythonCodeReview


class TestCodeReviewSelfContained:
    def test_returns_claude_agent_node(self):
        node = PythonCodeReview()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "python_code_review"
