from __future__ import annotations

from langclaude.nodes.resolve_findings import resolve_findings_node
from langclaude.nodes.base import ClaudeAgentNode


class TestResolveFindings:
    def test_constructs_with_defaults(self):
        node = resolve_findings_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "resolve_findings"

    def test_allow_includes_edit_write(self):
        node = resolve_findings_node()
        assert "Edit" in node.allow
        assert "Write" in node.allow

    def test_deny_includes_pip_install(self):
        node = resolve_findings_node()
        assert any("pip install" in d for d in node.deny)
