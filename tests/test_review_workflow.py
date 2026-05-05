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


class TestReviewWorkflowArchitecturePhase:
    def test_has_architecture_phase(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "architecture" in phase_names

    def test_architecture_runs_after_review(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        review_idx = phase_names.index("review")
        arch_idx = phase_names.index("architecture")
        assert arch_idx == review_idx + 1

    def test_architecture_runs_before_triage(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        arch_idx = phase_names.index("architecture")
        triage_idx = phase_names.index("triage")
        assert arch_idx < triage_idx

    def test_architecture_phase_is_automated(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_review_workflow()
        arch = next(p for p in workflow.phases if p.name == "architecture")
        assert arch.phase_type == PhaseType.AUTOMATED


class TestReviewWorkflowAutoFix:
    def test_auto_fix_false_triage_is_gate(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_review_workflow(auto_fix=False)
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE

    def test_auto_fix_true_triage_is_automated(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_review_workflow(auto_fix=True)
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.AUTOMATED
