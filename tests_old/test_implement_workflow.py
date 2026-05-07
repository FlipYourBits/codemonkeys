from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


from codemonkeys.artifacts.schemas.plans import FeaturePlan
from codemonkeys.artifacts.schemas.results import VerificationResult
from codemonkeys.workflows.implement import (
    _approve,
    _implement,
    _plan,
    _verify,
    make_implement_workflow,
)
from codemonkeys.workflows.phases import PhaseType, WorkflowContext


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


# ---------------------------------------------------------------------------
# Async phase characterization tests
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, **overrides) -> WorkflowContext:
    defaults = dict(
        cwd=str(tmp_path),
        run_id="test-run",
        phase_results={},
        user_input=None,
        config=None,
        emitter=None,
        log_dir=tmp_path,
    )
    defaults.update(overrides)
    return WorkflowContext(**defaults)


class TestPlanPhase:
    async def test_plan_returns_feature_plan(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, user_input="Add a login feature")
        result = await _plan(ctx)
        assert "plan" in result
        assert isinstance(result["plan"], FeaturePlan)

    async def test_plan_title_truncated_to_80_chars(self, tmp_path: Path) -> None:
        long_desc = "A" * 120
        ctx = _make_ctx(tmp_path, user_input=long_desc)
        result = await _plan(ctx)
        assert len(result["plan"].title) == 80

    async def test_plan_title_equals_description_when_short(
        self, tmp_path: Path
    ) -> None:
        desc = "Short description"
        ctx = _make_ctx(tmp_path, user_input=desc)
        result = await _plan(ctx)
        assert result["plan"].title == desc

    async def test_plan_description_matches_user_input(self, tmp_path: Path) -> None:
        desc = "Build an auth module"
        ctx = _make_ctx(tmp_path, user_input=desc)
        result = await _plan(ctx)
        assert result["plan"].description == desc

    async def test_plan_steps_is_empty_list(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, user_input="Anything")
        result = await _plan(ctx)
        assert result["plan"].steps == []

    async def test_plan_saves_artifact_to_disk(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, user_input="Save me")
        await _plan(ctx)
        artifact_path = tmp_path / ".codemonkeys" / "test-run" / "plan.json"
        assert artifact_path.exists()

    async def test_plan_artifact_is_valid_json(self, tmp_path: Path) -> None:
        import json

        ctx = _make_ctx(tmp_path, user_input="Validate JSON")
        await _plan(ctx)
        artifact_path = tmp_path / ".codemonkeys" / "test-run" / "plan.json"
        data = json.loads(artifact_path.read_text())
        assert data["description"] == "Validate JSON"

    async def test_plan_empty_user_input_produces_empty_title(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path, user_input=None)
        result = await _plan(ctx)
        assert result["plan"].title == ""
        assert result["plan"].description == ""


class TestApprovePhase:
    async def test_approve_returns_user_input_as_approved_plan(
        self, tmp_path: Path
    ) -> None:
        plan = FeaturePlan(title="T", description="D", steps=[])
        ctx = _make_ctx(tmp_path, user_input=plan)
        result = await _approve(ctx)
        assert result["approved_plan"] is plan

    async def test_approve_passes_none_through(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, user_input=None)
        result = await _approve(ctx)
        assert result["approved_plan"] is None

    async def test_approve_passes_string_through(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path, user_input="raw string input")
        result = await _approve(ctx)
        assert result["approved_plan"] == "raw string input"


class TestVerifyPhase:
    def _make_completed(
        self, returncode: int, stdout: str = ""
    ) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=""
        )

    async def test_verify_tests_passed_when_pytest_returns_zero(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        passing = self._make_completed(0, "1 passed")
        with patch("subprocess.run", return_value=passing):
            result = await _verify(ctx)
        assert result["verification"].tests_passed is True
        assert result["verification"].lint_passed is True

    async def test_verify_tests_failed_when_pytest_returns_nonzero(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        failing_tests = self._make_completed(1, "1 failed")
        passing_lint = self._make_completed(0, "")
        with patch("subprocess.run", side_effect=[failing_tests, passing_lint]):
            result = await _verify(ctx)
        assert result["verification"].tests_passed is False
        assert result["verification"].lint_passed is True

    async def test_verify_lint_failed_when_ruff_returns_nonzero(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        passing_tests = self._make_completed(0, "1 passed")
        failing_lint = self._make_completed(1, "E501 line too long")
        with patch("subprocess.run", side_effect=[passing_tests, failing_lint]):
            result = await _verify(ctx)
        assert result["verification"].tests_passed is True
        assert result["verification"].lint_passed is False

    async def test_verify_errors_list_populated_when_tests_fail(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        failing = self._make_completed(1, "FAILED test_x.py::test_y")
        passing = self._make_completed(0, "")
        with patch("subprocess.run", side_effect=[failing, passing]):
            result = await _verify(ctx)
        errors = result["verification"].errors
        assert len(errors) == 1
        assert "pytest" in errors[0]

    async def test_verify_errors_list_has_lint_entry_when_ruff_fails(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        passing = self._make_completed(0, "")
        failing_lint = self._make_completed(1, "E501 line too long")
        with patch("subprocess.run", side_effect=[passing, failing_lint]):
            result = await _verify(ctx)
        errors = result["verification"].errors
        assert any("ruff" in e for e in errors)

    async def test_verify_returns_verification_result_model(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)
        passing = self._make_completed(0, "")
        with patch("subprocess.run", return_value=passing):
            result = await _verify(ctx)
        assert isinstance(result["verification"], VerificationResult)

    async def test_verify_typecheck_always_passes(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        passing = self._make_completed(0, "")
        with patch("subprocess.run", return_value=passing):
            result = await _verify(ctx)
        assert result["verification"].typecheck_passed is True

    async def test_verify_stdout_truncated_to_500_chars(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        long_stdout = "X" * 1000
        failing = self._make_completed(1, long_stdout)
        passing = self._make_completed(0, "")
        with patch("subprocess.run", side_effect=[failing, passing]):
            result = await _verify(ctx)
        error_msg = result["verification"].errors[0]
        # The raw stdout slice is capped at 500.
        assert len(error_msg) <= len("pytest: ") + 500 + 10


class TestImplementPhase:
    """Tests for _implement() — the phase that runs the python_implementer agent."""

    async def test_implement_calls_agent_runner(self, tmp_path: Path) -> None:
        """_implement() should create an AgentRunner and call run_agent."""
        plan = FeaturePlan(title="Test plan", description="Do stuff", steps=[])
        ctx = _make_ctx(
            tmp_path,
            phase_results={"approve": {"approved_plan": plan}},
        )

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "done"
        mock_runner.run_agent = AsyncMock(return_value=mock_result)

        # AgentRunner is imported locally inside _implement, so patch at source.
        with (
            patch("codemonkeys.core.runner.AgentRunner", return_value=mock_runner),
            patch(
                "codemonkeys.workflows.implement.make_python_implementer",
                return_value=MagicMock(),
            ),
        ):
            result = await _implement(ctx)

        mock_runner.run_agent.assert_awaited_once()
        assert result["result"] == "done"

    async def test_implement_saves_approved_plan_artifact(self, tmp_path: Path) -> None:
        """_implement() saves the approved plan before running the agent."""
        plan = FeaturePlan(title="Save test", description="Persist me", steps=[])
        ctx = _make_ctx(
            tmp_path,
            phase_results={"approve": {"approved_plan": plan}},
        )

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "ok"
        mock_runner.run_agent = AsyncMock(return_value=mock_result)

        with (
            patch("codemonkeys.core.runner.AgentRunner", return_value=mock_runner),
            patch(
                "codemonkeys.workflows.implement.make_python_implementer",
                return_value=MagicMock(),
            ),
        ):
            await _implement(ctx)

        artifact = tmp_path / ".codemonkeys" / "test-run" / "approved-plan.json"
        assert artifact.exists()

    async def test_implement_prompt_contains_plan_json(self, tmp_path: Path) -> None:
        """The prompt passed to run_agent includes the plan's JSON representation."""
        plan = FeaturePlan(title="JSON check", description="Has steps", steps=[])
        ctx = _make_ctx(
            tmp_path,
            phase_results={"approve": {"approved_plan": plan}},
        )

        captured_prompt: list[str] = []
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "done"

        async def _capture_run(agent, prompt, **kwargs):
            captured_prompt.append(prompt)
            return mock_result

        mock_runner.run_agent = _capture_run

        with (
            patch("codemonkeys.core.runner.AgentRunner", return_value=mock_runner),
            patch(
                "codemonkeys.workflows.implement.make_python_implementer",
                return_value=MagicMock(),
            ),
        ):
            await _implement(ctx)

        assert captured_prompt
        assert "JSON check" in captured_prompt[0]


class TestAutoReviewPhase:
    """Tests for _auto_review() — runs the review pipeline after implementation.

    The phase functions are imported locally inside _auto_review(), so we patch
    them at their source modules in the phase_library package.
    """

    async def test_auto_review_returns_findings_and_fix_results_when_fixes_needed(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)

        discover_result = {"files": ["a.py"]}
        file_result = {"file_findings": [{"file": "a.py", "findings": []}]}
        arch_result = {"architecture_findings": None}
        triage_result = {"fix_requests": ["fix it"]}
        fix_result = {"fix_results": ["fixed"]}

        # _auto_review imports from the package-level re-exports and the
        # discovery submodule directly, so patch at those locations.
        with (
            patch(
                "codemonkeys.workflows.phase_library.discovery.discover_diff",
                AsyncMock(return_value=discover_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.file_review",
                AsyncMock(return_value=file_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.architecture_review",
                AsyncMock(return_value=arch_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.triage",
                AsyncMock(return_value=triage_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.fix",
                AsyncMock(return_value=fix_result),
            ),
        ):
            from codemonkeys.workflows.implement import _auto_review

            result = await _auto_review(ctx)

        assert "findings" in result
        assert "fix_results" in result
        assert result["fix_results"] == ["fixed"]

    async def test_auto_review_returns_empty_fix_results_when_no_fixes_needed(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)

        discover_result = {"files": []}
        file_result = {"file_findings": []}
        arch_result = {"architecture_findings": None}
        triage_result = {"fix_requests": []}  # empty — no fixes needed

        with (
            patch(
                "codemonkeys.workflows.phase_library.discovery.discover_diff",
                AsyncMock(return_value=discover_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.file_review",
                AsyncMock(return_value=file_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.architecture_review",
                AsyncMock(return_value=arch_result),
            ),
            patch(
                "codemonkeys.workflows.phase_library.triage",
                AsyncMock(return_value=triage_result),
            ),
        ):
            from codemonkeys.workflows.implement import _auto_review

            result = await _auto_review(ctx)

        assert result["fix_results"] == []

    async def test_auto_review_architecture_findings_propagated(
        self, tmp_path: Path
    ) -> None:
        ctx = _make_ctx(tmp_path)

        arch_finding = {"issue": "circular import"}
        with (
            patch(
                "codemonkeys.workflows.phase_library.discovery.discover_diff",
                AsyncMock(return_value={}),
            ),
            patch(
                "codemonkeys.workflows.phase_library.file_review",
                AsyncMock(return_value={"file_findings": []}),
            ),
            patch(
                "codemonkeys.workflows.phase_library.architecture_review",
                AsyncMock(return_value={"architecture_findings": arch_finding}),
            ),
            patch(
                "codemonkeys.workflows.phase_library.triage",
                AsyncMock(return_value={"fix_requests": []}),
            ),
        ):
            from codemonkeys.workflows.implement import _auto_review

            result = await _auto_review(ctx)

        assert result["architecture_findings"] == arch_finding
