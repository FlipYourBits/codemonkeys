from __future__ import annotations

from langclaude.nodes.code_review import code_review_node


class TestCodeReviewSelfContained:
    def test_returns_async_callable(self):
        node = code_review_node()
        assert callable(node)
        assert hasattr(node, "declared_outputs")
        assert "code_review" in node.declared_outputs

    def test_custom_name(self):
        node = code_review_node(name="my_review")
        assert node.__name__ == "my_review"
        assert "my_review" in node.declared_outputs
