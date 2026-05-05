from __future__ import annotations


from codemonkeys.workflows.review import make_review_workflow


class TestReviewWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "discover" in phase_names
        assert "review" in phase_names
        assert "triage" in phase_names
        assert "fix" in phase_names
        assert "verify" in phase_names

    def test_triage_is_a_gate(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_review_workflow()
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE

    def test_has_report_phase(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "report" in phase_names
