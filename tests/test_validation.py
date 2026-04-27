from __future__ import annotations

import pytest

from langclaude import (
    OutputKeyConflict,
    claude_code_review_node,
    claude_coverage_node,
    claude_dependency_audit_node,
    claude_pytest_node,
    claude_security_audit_node,
    validate_node_outputs,
)


class TestValidateNodeOutputs:
    def test_clean_pipeline_passes(self):
        validate_node_outputs(
            claude_dependency_audit_node(),
            claude_security_audit_node(),
            claude_code_review_node(),
            claude_coverage_node(),
            claude_pytest_node(),
        )

    def test_two_security_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="security_findings"):
            validate_node_outputs(
                claude_security_audit_node(),
                claude_security_audit_node(),
            )

    def test_two_review_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="review_findings"):
            validate_node_outputs(
                claude_code_review_node(),
                claude_code_review_node(),
            )

    def test_distinct_output_keys_resolve_conflict(self):
        validate_node_outputs(
            claude_security_audit_node(name="sec_diff", output_key="security_findings"),
            claude_security_audit_node(name="sec_full", output_key="security_findings_full"),
        )

    def test_last_cost_usd_is_merge_ok(self):
        # Both are ClaudeAgentNode-based and both write last_cost_usd —
        # that key is on the merge-OK allow-list, so no conflict.
        validate_node_outputs(
            claude_security_audit_node(),
            claude_code_review_node(),
        )

    def test_node_without_declared_outputs_silently_skipped(self):
        async def bare(state):
            return {}

        # No declared_outputs → no contribution to the conflict check.
        validate_node_outputs(bare, claude_code_review_node())

    def test_error_message_lists_owners(self):
        with pytest.raises(OutputKeyConflict) as exc:
            validate_node_outputs(
                claude_security_audit_node(name="audit_one"),
                claude_security_audit_node(name="audit_two"),
            )
        msg = str(exc.value)
        assert "audit_one" in msg and "audit_two" in msg
        assert "security_findings" in msg
