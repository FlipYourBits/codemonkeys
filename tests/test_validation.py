from __future__ import annotations

import pytest

from codemonkeys import (
    OutputKeyConflict,
    PythonCodeReview,
    PythonDependencyAudit,
    PythonSecurityAudit,
    PythonTest,
    validate_node_outputs,
)


class TestValidateNodeOutputs:
    def test_clean_pipeline_passes(self):
        validate_node_outputs(
            PythonDependencyAudit(),
            PythonSecurityAudit(),
            PythonCodeReview(),
            PythonTest(),
        )

    def test_two_security_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="python_security_audit"):
            validate_node_outputs(
                PythonSecurityAudit(),
                PythonSecurityAudit(),
            )

    def test_two_review_nodes_default_conflict(self):
        with pytest.raises(OutputKeyConflict, match="python_code_review"):
            validate_node_outputs(
                PythonCodeReview(),
                PythonCodeReview(),
            )

    def test_last_cost_usd_is_merge_ok(self):
        validate_node_outputs(
            PythonSecurityAudit(),
            PythonCodeReview(),
        )

    def test_node_without_declared_outputs_silently_skipped(self):
        async def bare(state):
            return {}

        validate_node_outputs(bare, PythonCodeReview())

    def test_error_message_lists_owners(self):
        with pytest.raises(OutputKeyConflict) as exc:
            validate_node_outputs(
                PythonSecurityAudit(),
                PythonSecurityAudit(),
            )
        msg = str(exc.value)
        assert "python_security_audit" in msg
