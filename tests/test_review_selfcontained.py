from __future__ import annotations

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.nodes.code_review import claude_code_review_node


class TestCodeReviewSelfContained:
    def test_default_is_readonly(self):
        node = claude_code_review_node()
        assert isinstance(node, ClaudeAgentNode)
        assert "Edit" in node.deny
        assert "Write" in node.deny

    def test_allow_edit_write_removes_from_deny(self):
        node = claude_code_review_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)", "Bash(git commit*)"],
        )
        assert isinstance(node, ClaudeAgentNode)
        assert "Edit" not in node.deny
        assert "Write" not in node.deny

    def test_system_prompt_includes_fix_when_write_allowed(self):
        node = claude_code_review_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)"],
        )
        assert (
            "fix" in node.system_prompt.lower() or "edit" in node.system_prompt.lower()
        )
