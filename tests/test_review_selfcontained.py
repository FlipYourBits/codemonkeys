from __future__ import annotations

from agentpipe.nodes.base import ClaudeAgentNode
from agentpipe.nodes._old.code_review import code_review_node


class TestCodeReviewSelfContained:
    def test_returns_claude_agent_node(self):
        node = code_review_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "code_review"

    def test_custom_name(self):
        node = code_review_node(name="my_review")
        assert node.name == "my_review"
