from __future__ import annotations

from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.core.agents.spec_compliance_reviewer import (
    make_spec_compliance_reviewer,
)


def _sample_spec() -> FeaturePlan:
    return FeaturePlan(
        title="Widget Factory",
        description="Add a widget factory that produces widgets from templates.",
        steps=[
            PlanStep(
                description="Create widget schema",
                files=["src/schemas/widget.py"],
            ),
            PlanStep(
                description="Implement factory function",
                files=["src/factory.py", "src/templates.py"],
            ),
            PlanStep(
                description="Add unit tests",
                files=["tests/test_factory.py"],
            ),
        ],
    )


def _make(**overrides):
    defaults = {
        "spec": _sample_spec(),
        "files": [
            "src/schemas/widget.py",
            "src/factory.py",
            "src/templates.py",
            "tests/test_factory.py",
        ],
        "unplanned_files": ["src/utils.py"],
    }
    defaults.update(overrides)
    return make_spec_compliance_reviewer(**defaults)


class TestSpecComplianceReviewer:
    def test_returns_agent_definition_with_correct_model(self) -> None:
        agent = _make()
        assert agent.model == "opus"

    def test_has_read_and_grep_tools(self) -> None:
        agent = _make()
        assert "Read" in agent.tools
        assert "Grep" in agent.tools

    def test_permission_mode_is_dont_ask(self) -> None:
        agent = _make()
        assert agent.permissionMode == "dontAsk"

    def test_prompt_contains_spec_step_descriptions(self) -> None:
        agent = _make()
        assert "Create widget schema" in agent.prompt
        assert "Implement factory function" in agent.prompt
        assert "Add unit tests" in agent.prompt

    def test_prompt_mentions_unplanned_files(self) -> None:
        agent = _make()
        assert "src/utils.py" in agent.prompt

    def test_prompt_no_unplanned_files_message(self) -> None:
        agent = _make(unplanned_files=[])
        assert "(none — all changed files are in the spec)" in agent.prompt

    def test_prompt_contains_all_checklist_categories(self) -> None:
        agent = _make()
        assert "completeness" in agent.prompt
        assert "scope_creep" in agent.prompt
        assert "contract_compliance" in agent.prompt
        assert "behavioral_fidelity" in agent.prompt
        assert "test_coverage" in agent.prompt

    def test_description_includes_spec_title(self) -> None:
        agent = _make()
        assert "Widget Factory" in agent.description

    def test_prompt_contains_implementation_files(self) -> None:
        agent = _make()
        assert "src/factory.py" in agent.prompt
        assert "tests/test_factory.py" in agent.prompt


class TestSpecComplianceReviewerRegistry:
    def test_registered_in_default_registry(self) -> None:
        from codemonkeys.core.agents import default_registry

        registry = default_registry()
        spec = registry.get("spec-compliance-reviewer")
        assert spec is not None
        assert spec.name == "spec-compliance-reviewer"

    def test_registry_role_is_analyzer(self) -> None:
        from codemonkeys.core.agents import default_registry
        from codemonkeys.core.agents.registry import AgentRole

        registry = default_registry()
        spec = registry.get("spec-compliance-reviewer")
        assert spec.role == AgentRole.ANALYZER

    def test_registry_scope_is_project(self) -> None:
        from codemonkeys.core.agents import default_registry

        registry = default_registry()
        spec = registry.get("spec-compliance-reviewer")
        assert spec.scope == "project"
