"""Characterization tests for codemonkeys/run_review.py."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.run_review import (
    _handle_refactor_gate,
    _handle_triage_gate,
    _init_log_dir,
    _pick_workflow,
    _resolve_mode,
    main_async,
)
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.events import EventType, WaitingForUserPayload


# ---------------------------------------------------------------------------
# _init_log_dir
# ---------------------------------------------------------------------------


class TestInitLogDir:
    def test_creates_directory_under_codemonkeys_logs(self, tmp_path: Path) -> None:
        log_dir = _init_log_dir(tmp_path)
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_returns_path_inside_codemonkeys_logs(self, tmp_path: Path) -> None:
        log_dir = _init_log_dir(tmp_path)
        assert log_dir.parent.parent == tmp_path / ".codemonkeys"

    def test_directory_name_has_timestamp_format(self, tmp_path: Path) -> None:
        log_dir = _init_log_dir(tmp_path)
        # Name matches YYYY-MM-DD_HH-MM-SS
        name = log_dir.name
        parts = name.split("_")
        assert len(parts) == 2
        assert len(parts[0]) == 10  # YYYY-MM-DD
        assert len(parts[1]) == 8  # HH-MM-SS

    def test_nested_directory_created_on_first_call(self, tmp_path: Path) -> None:
        _init_log_dir(tmp_path)
        assert (tmp_path / ".codemonkeys" / "logs").is_dir()


# ---------------------------------------------------------------------------
# _resolve_mode
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {"files": None, "diff": False, "repo": False, "deep_clean": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestResolveMode:
    def test_files_flag_returns_files(self) -> None:
        args = _make_args(files=["a.py"])
        assert _resolve_mode(args) == "files"

    def test_diff_flag_returns_diff(self) -> None:
        args = _make_args(diff=True)
        assert _resolve_mode(args) == "diff"

    def test_repo_flag_returns_repo(self) -> None:
        args = _make_args(repo=True)
        assert _resolve_mode(args) == "repo"

    def test_deep_clean_flag_returns_deep_clean(self) -> None:
        args = _make_args(deep_clean=True)
        assert _resolve_mode(args) == "deep_clean"

    def test_no_flags_delegates_to_select_mode(self) -> None:
        args = _make_args()
        with patch(
            "codemonkeys.run_review._select_mode", return_value="diff"
        ) as mock_sel:
            result = _resolve_mode(args)
        mock_sel.assert_called_once()
        assert result == "diff"


# ---------------------------------------------------------------------------
# _select_mode (via mocked console.input)
# ---------------------------------------------------------------------------


class TestSelectMode:
    def test_input_2_returns_repo(self) -> None:
        from codemonkeys import run_review

        with (
            patch.object(run_review.console, "input", return_value="2"),
            patch.object(run_review.console, "print"),
        ):
            from codemonkeys.run_review import _select_mode

            assert _select_mode() == "repo"

    def test_any_other_input_returns_diff(self) -> None:
        from codemonkeys import run_review

        for val in ("1", "3", "", "foo"):
            with (
                patch.object(run_review.console, "input", return_value=val),
                patch.object(run_review.console, "print"),
            ):
                from codemonkeys.run_review import _select_mode

                assert _select_mode() == "diff", f"Expected 'diff' for input {val!r}"


# ---------------------------------------------------------------------------
# _pick_workflow
# ---------------------------------------------------------------------------


class TestPickWorkflow:
    def _config(self, mode: str, auto_fix: bool = False) -> ReviewConfig:
        return ReviewConfig(mode=mode, auto_fix=auto_fix)  # type: ignore[arg-type]

    def test_files_mode_returns_files_review_workflow(self) -> None:
        wf = _pick_workflow(self._config("files"))
        assert wf.name == "files_review"

    def test_diff_mode_returns_diff_review_workflow(self) -> None:
        wf = _pick_workflow(self._config("diff"))
        assert wf.name == "diff_review"

    def test_repo_mode_returns_repo_review_workflow(self) -> None:
        wf = _pick_workflow(self._config("repo"))
        assert wf.name == "repo_review"

    def test_post_feature_mode_returns_post_feature_workflow(self) -> None:
        wf = _pick_workflow(self._config("post_feature"))
        assert wf.name == "post_feature_review"

    def test_deep_clean_mode_returns_deep_clean_workflow(self) -> None:
        wf = _pick_workflow(self._config("deep_clean"))
        assert wf.name == "deep_clean"

    def test_auto_fix_true_propagates_to_diff_workflow(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        wf = _pick_workflow(self._config("diff", auto_fix=True))
        triage = next(p for p in wf.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.AUTOMATED

    def test_auto_fix_false_makes_triage_a_gate(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        wf = _pick_workflow(self._config("diff", auto_fix=False))
        triage = next(p for p in wf.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE


# ---------------------------------------------------------------------------
# _handle_refactor_gate
# ---------------------------------------------------------------------------


class TestHandleRefactorGate:
    def _make_mocks(self):
        engine = MagicMock()
        display = MagicMock()
        return engine, display

    def test_empty_input_resolves_skip(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value=""),
            patch.object(run_review.console, "print"),
        ):
            _handle_refactor_gate(engine, display, "refactor_naming")
        engine.resolve_gate.assert_called_once_with("skip")

    def test_skip_literal_resolves_skip(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="skip"),
            patch.object(run_review.console, "print"),
        ):
            _handle_refactor_gate(engine, display, "refactor_naming")
        engine.resolve_gate.assert_called_once_with("skip")

    def test_approve_resolves_approve(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="approve"),
            patch.object(run_review.console, "print"),
        ):
            _handle_refactor_gate(engine, display, "refactor_naming")
        engine.resolve_gate.assert_called_once_with("approve")

    def test_any_nonempty_non_skip_resolves_approve(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="yes please"),
            patch.object(run_review.console, "print"),
        ):
            _handle_refactor_gate(engine, display, "refactor_naming")
        engine.resolve_gate.assert_called_once_with("approve")

    def test_display_paused_and_resumed(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="approve"),
            patch.object(run_review.console, "print"),
        ):
            _handle_refactor_gate(engine, display, "refactor_naming")
        display.pause.assert_called_once()
        display.resume.assert_called_once()

    def test_step_label_derived_from_phase_name(self) -> None:
        """Phase name 'refactor_naming' → step label 'Naming' in panel title."""
        from codemonkeys import run_review
        from rich.panel import Panel

        engine, display = self._make_mocks()
        printed_panels: list[Panel] = []
        with (
            patch.object(run_review.console, "input", return_value="skip"),
            patch.object(
                run_review.console, "print", side_effect=printed_panels.append
            ),
        ):
            _handle_refactor_gate(engine, display, "refactor_god_modules")
        assert printed_panels  # at least one panel was printed


# ---------------------------------------------------------------------------
# _handle_triage_gate
# ---------------------------------------------------------------------------


class TestHandleTriageGate:
    def _make_mocks(self):
        engine = MagicMock()
        display = MagicMock()
        return engine, display

    def test_empty_input_resolves_empty_list(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value=""),
            patch.object(run_review.console, "print"),
        ):
            _handle_triage_gate(engine, display)
        engine.resolve_gate.assert_called_once_with([])

    def test_skip_literal_resolves_empty_list(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="skip"),
            patch.object(run_review.console, "print"),
        ):
            _handle_triage_gate(engine, display)
        engine.resolve_gate.assert_called_once_with([])

    def test_natural_language_input_resolves_as_string(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="fix everything"),
            patch.object(run_review.console, "print"),
        ):
            _handle_triage_gate(engine, display)
        engine.resolve_gate.assert_called_once_with("fix everything")

    def test_display_paused_and_resumed(self) -> None:
        from codemonkeys import run_review

        engine, display = self._make_mocks()
        with (
            patch.object(run_review.console, "input", return_value="skip"),
            patch.object(run_review.console, "print"),
        ):
            _handle_triage_gate(engine, display)
        display.pause.assert_called_once()
        display.resume.assert_called_once()


# ---------------------------------------------------------------------------
# main_async — integration-style test with fully mocked infrastructure
# ---------------------------------------------------------------------------


def _make_main_args(
    *,
    files=None,
    diff: bool = False,
    repo: bool = False,
    deep_clean: bool = False,
    auto_fix: bool = False,
    graph: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        files=files,
        diff=diff,
        repo=repo,
        deep_clean=deep_clean,
        auto_fix=auto_fix,
        graph=graph,
    )


class TestMainAsync:
    async def test_main_async_runs_to_completion(self, tmp_path: Path) -> None:
        from codemonkeys import run_review

        args = _make_main_args(diff=True)

        mock_display = MagicMock()
        mock_display.start = MagicMock()
        mock_display.stop = MagicMock()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock()

        with (
            patch("codemonkeys.run_review.restrict"),
            patch(
                "codemonkeys.run_review._init_log_dir",
                return_value=tmp_path / ".codemonkeys" / "logs" / "ts",
            ),
            patch("codemonkeys.run_review.WorkflowDisplay", return_value=mock_display),
            patch("codemonkeys.run_review.WorkflowEngine", return_value=mock_engine),
            patch.object(run_review.console, "print"),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            await main_async(args)

        mock_engine.run.assert_awaited_once()
        mock_display.start.assert_called_once()
        mock_display.stop.assert_called_once()

    async def test_main_async_stop_called_even_on_exception(
        self, tmp_path: Path
    ) -> None:
        from codemonkeys import run_review

        args = _make_main_args(diff=True)

        mock_display = MagicMock()
        mock_display.start = MagicMock()
        mock_display.stop = MagicMock()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch("codemonkeys.run_review.restrict"),
            patch(
                "codemonkeys.run_review._init_log_dir",
                return_value=tmp_path / ".codemonkeys" / "logs" / "ts",
            ),
            patch("codemonkeys.run_review.WorkflowDisplay", return_value=mock_display),
            patch("codemonkeys.run_review.WorkflowEngine", return_value=mock_engine),
            patch.object(run_review.console, "print"),
            patch("pathlib.Path.cwd", return_value=tmp_path),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await main_async(args)

        mock_display.stop.assert_called_once()

    async def test_main_async_on_waiting_triage_calls_handle_triage(
        self, tmp_path: Path
    ) -> None:
        """When WAITING_FOR_USER fires without refactor_ prefix, _handle_triage_gate is called."""
        from codemonkeys import run_review

        args = _make_main_args(diff=True)

        captured_handlers: list = []

        def _capture_on(event_type, callback):
            if event_type == EventType.WAITING_FOR_USER:
                captured_handlers.append(callback)

        mock_emitter = MagicMock()
        mock_emitter.on = _capture_on

        mock_display = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = AsyncMock()
        mock_engine.resolve_gate = MagicMock()

        with (
            patch("codemonkeys.run_review.restrict"),
            patch(
                "codemonkeys.run_review._init_log_dir",
                return_value=tmp_path / ".codemonkeys" / "logs" / "ts",
            ),
            patch("codemonkeys.run_review.EventEmitter", return_value=mock_emitter),
            patch("codemonkeys.run_review.WorkflowDisplay", return_value=mock_display),
            patch("codemonkeys.run_review.WorkflowEngine", return_value=mock_engine),
            patch.object(run_review.console, "print"),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            await main_async(args)

        assert len(captured_handlers) == 1
        payload = WaitingForUserPayload(phase="triage", workflow="diff_review")
        with (
            patch("codemonkeys.run_review._handle_triage_gate") as mock_triage,
            patch("codemonkeys.run_review._handle_refactor_gate") as mock_refactor,
        ):
            captured_handlers[0](EventType.WAITING_FOR_USER, payload)
        mock_triage.assert_called_once()
        mock_refactor.assert_not_called()

    async def test_main_async_on_waiting_refactor_calls_handle_refactor(
        self, tmp_path: Path
    ) -> None:
        """When WAITING_FOR_USER fires with refactor_ prefix, _handle_refactor_gate is called."""
        from codemonkeys import run_review

        args = _make_main_args(diff=True)
        captured_handlers: list = []

        def _capture_on(event_type, callback):
            if event_type == EventType.WAITING_FOR_USER:
                captured_handlers.append(callback)

        mock_emitter = MagicMock()
        mock_emitter.on = _capture_on

        mock_display = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = AsyncMock()

        with (
            patch("codemonkeys.run_review.restrict"),
            patch(
                "codemonkeys.run_review._init_log_dir",
                return_value=tmp_path / ".codemonkeys" / "logs" / "ts",
            ),
            patch("codemonkeys.run_review.EventEmitter", return_value=mock_emitter),
            patch("codemonkeys.run_review.WorkflowDisplay", return_value=mock_display),
            patch("codemonkeys.run_review.WorkflowEngine", return_value=mock_engine),
            patch.object(run_review.console, "print"),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            await main_async(args)

        assert len(captured_handlers) == 1
        payload = WaitingForUserPayload(phase="refactor_naming", workflow="deep_clean")
        with (
            patch("codemonkeys.run_review._handle_refactor_gate") as mock_refactor,
            patch("codemonkeys.run_review._handle_triage_gate") as mock_triage,
        ):
            captured_handlers[0](EventType.WAITING_FOR_USER, payload)
        mock_refactor.assert_called_once()
        mock_triage.assert_not_called()
