from __future__ import annotations

from codemonkeys.workflows.implement import make_implement_workflow
from codemonkeys.workflows.phases import PhaseType


class TestImplementWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_implement_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "plan" in phase_names
        assert "approve" in phase_names
        assert "implement" in phase_names
        assert "verify" in phase_names

    def test_approve_is_a_gate(self) -> None:
        workflow = make_implement_workflow()
        approve = next(p for p in workflow.phases if p.name == "approve")
        assert approve.phase_type == PhaseType.GATE

    def test_plan_is_interactive(self) -> None:
        workflow = make_implement_workflow()
        plan = next(p for p in workflow.phases if p.name == "plan")
        assert plan.phase_type == PhaseType.INTERACTIVE


class TestImplementWorkflowWithReview:
    def test_has_review_phase(self) -> None:
        workflow = make_implement_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "review" in phase_names

    def test_review_runs_after_implement(self) -> None:
        workflow = make_implement_workflow()
        phase_names = [p.name for p in workflow.phases]
        impl_idx = phase_names.index("implement")
        review_idx = phase_names.index("review")
        assert review_idx == impl_idx + 1

    def test_review_is_automated(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_implement_workflow()
        review = next(p for p in workflow.phases if p.name == "review")
        assert review.phase_type == PhaseType.AUTOMATED
