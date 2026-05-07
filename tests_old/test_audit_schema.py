from __future__ import annotations

import pytest

from codemonkeys.artifacts.schemas.audit import AgentAudit, Issue


class TestAuditSchema:
    def test_issue_round_trips(self):
        issue = Issue(
            category="unauthorized_tool",
            turn=3,
            description="Agent called Bash but only Read is allowed",
            evidence='{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}',
        )
        data = issue.model_dump()
        assert data["category"] == "unauthorized_tool"
        assert data["turn"] == 3
        rebuilt = Issue.model_validate(data)
        assert rebuilt == issue

    def test_issue_turn_is_optional(self):
        issue = Issue(
            category="off_task",
            turn=None,
            description="Agent reasoning went off-topic",
            evidence="Thinking block about unrelated file",
        )
        assert issue.turn is None

    def test_agent_audit_pass_verdict(self):
        audit = AgentAudit(
            agent_name="changelog_reviewer",
            verdict="pass",
            summary="Agent completed the review correctly and efficiently.",
            issues=[],
            token_assessment="Reasonable token usage for the task.",
            recommendations=[],
        )
        schema = AgentAudit.model_json_schema()
        assert "verdict" in schema["properties"]
        assert audit.verdict == "pass"

    def test_agent_audit_fail_with_issues(self):
        audit = AgentAudit(
            agent_name="readme_reviewer",
            verdict="fail",
            summary="Agent used unauthorized tools and went off-task.",
            issues=[
                Issue(
                    category="unauthorized_tool",
                    turn=5,
                    description="Called Write tool",
                    evidence="tool_use Write",
                ),
                Issue(
                    category="off_task",
                    turn=7,
                    description="Spent 3 turns analyzing pyproject.toml",
                    evidence="Thinking: let me check the build config...",
                ),
            ],
            token_assessment="Excessive — 40k tokens for a simple review.",
            recommendations=["Add explicit constraint: do not modify files"],
        )
        assert audit.verdict == "fail"
        assert len(audit.issues) == 2

    def test_category_literal_rejects_invalid(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            Issue(
                category="invalid_category",
                turn=1,
                description="test",
                evidence="test",
            )

    def test_verdict_literal_rejects_invalid(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            AgentAudit(
                agent_name="test",
                verdict="maybe",
                summary="test",
                issues=[],
                token_assessment="test",
                recommendations=[],
            )
