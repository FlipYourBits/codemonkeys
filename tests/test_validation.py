from __future__ import annotations

import pytest

from agentpipe import (
    OutputKeyConflict,
    code_review_node,
    python_coverage_node,
    python_dependency_audit_node,
    python_test_node,
    security_audit_node,
    validate_node_outputs,
)


class TestValidateNodeOutputs:
    def test_clean_pipeline_passes(self):
        validate_node_outputs(
            python_dependency_audit_node(),
            security_audit_node(),
            code_review_node(),
            python_coverage_node(),
            python_test_node(),
        )

    def test_two_security_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="security_audit"):
            validate_node_outputs(
                security_audit_node(),
                security_audit_node(),
            )

    def test_two_review_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="code_review"):
            validate_node_outputs(
                code_review_node(),
                code_review_node(),
            )

    def test_distinct_names_resolve_conflict(self):
        validate_node_outputs(
            security_audit_node(name="sec_diff"),
            security_audit_node(name="sec_full"),
        )

    def test_last_cost_usd_is_merge_ok(self):
        validate_node_outputs(
            security_audit_node(),
            code_review_node(),
        )

    def test_node_without_declared_outputs_silently_skipped(self):
        async def bare(state):
            return {}

        validate_node_outputs(bare, code_review_node())

    def test_error_message_lists_owners(self):
        with pytest.raises(OutputKeyConflict) as exc:
            validate_node_outputs(
                security_audit_node(name="audit_one"),
                security_audit_node(name="audit_one"),
            )
        msg = str(exc.value)
        assert "audit_one" in msg
