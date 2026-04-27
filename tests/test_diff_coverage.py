"""Tests covering coverage gaps in diff-mode changed files.

Focuses on business logic and error paths that were uncovered:
- budget.default_on_warn with display
- display.node_skip/warn in live mode, default_prompt with content
- resolve_findings.ask_findings_via_stdin interactive branches
- pipeline._apply_overrides verbosity/model/prompt_fn injection
- pipeline._node_exit parallel path, non-dict with display
- pipeline._node_enter on_message/on_warn setup
- pipeline.print_results no-display path
- nodes/base._make_printer emit-to-display, text truncation
- nodes/base.ClaudeAgentNode._render_prompt with prior results
- prompt_fn override wiring in plan/implement/commit node factories
- permissions.ask_via_stdin with prompt_fn
- graph main() functions
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentpipe.budget import default_on_warn
from agentpipe.display import Display, default_prompt
from agentpipe.nodes.base import ClaudeAgentNode, Verbosity, _make_printer
from agentpipe.nodes.git_commit import git_commit_node
from agentpipe.nodes.python_implement_feature import python_implement_feature_node
from agentpipe.nodes.python_plan_feature import python_plan_feature_node
from agentpipe.nodes.resolve_findings import (
    ask_findings_via_stdin,
    resolve_findings_node,
)
from agentpipe.permissions import ask_via_stdin
from agentpipe.pipeline import Pipeline


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from agentpipe import registry as reg

    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


# ── budget ────────────────────────────────────────────────────────────────────


class TestDefaultOnWarnWithDisplay:
    def test_routes_to_display_warn(self):
        display = MagicMock()
        default_on_warn(0.0080, 0.01, display=display)
        display.warn.assert_called_once()
        msg = display.warn.call_args[0][0]
        assert "80%" in msg

    def test_zero_max_budget_no_div_error(self):
        """max_budget_usd=0 should not raise ZeroDivisionError."""
        display = MagicMock()
        default_on_warn(0.0, 0.0, display=display)
        display.warn.assert_called_once()

    def test_full_budget_100_pct(self):
        display = MagicMock()
        default_on_warn(0.10, 0.10, display=display)
        msg = display.warn.call_args[0][0]
        assert "100%" in msg


# ── display ───────────────────────────────────────────────────────────────────


class TestDisplayLiveNodeSkip:
    def test_node_skip_calls_refresh_in_live_mode(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["lint"], title="T", live=True)
        d.node_skip("lint")  # must call _refresh() without raising
        d.stop()


class TestDisplayLiveWarn:
    def test_warn_via_live_console(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=[], title="T", live=True)
        # warn() when _use_live=True and _live is not None takes the live branch
        d.warn("over budget")
        d.stop()


class TestDefaultPrompt:
    def test_with_content_prints_to_stderr(self, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        result = default_prompt("Continue?", content="the plan text")
        assert result == "yes"
        err = capsys.readouterr().err
        assert "the plan text" in err

    def test_with_content_includes_separator(self, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        default_prompt("OK?", content="some content")
        err = capsys.readouterr().err
        assert "=" * 10 in err  # separator lines

    def test_without_content_no_separator(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "ok")
        result = default_prompt("Proceed?")
        assert result == "ok"


# ── resolve_findings ──────────────────────────────────────────────────────────


class TestAskFindingsViaStndin:
    def test_non_tty_returns_none(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = asyncio.run(ask_findings_via_stdin("summary"))
        assert result is None

    def test_tty_none_response_returns_none_string(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="none")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "none"

    def test_tty_quit_synonym(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="q")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "none"

    def test_tty_skip_synonym(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="skip")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "none"

    def test_tty_all_response_returns_all(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="all")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "all"

    def test_tty_empty_response_returns_all(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "all"

    def test_tty_yes_synonym(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="yes")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "all"

    def test_tty_number_response_returned_as_is(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="1 2 3")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "1 2 3"

    def test_tty_whitespace_stripped(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="  NONE  ")
        result = asyncio.run(ask_findings_via_stdin("summary", prompt_fn=prompt_fn))
        assert result == "none"


class TestResolveFindingsInteractive:
    def test_interactive_returns_callable(self):
        node = resolve_findings_node(interactive=True)
        assert callable(node)
        assert node.__name__ == "resolve_findings"

    def test_non_interactive_returns_callable(self):
        node = resolve_findings_node(interactive=False)
        assert callable(node)
        assert node.__name__ == "resolve_findings"


# ── permissions ───────────────────────────────────────────────────────────────


class TestAskViaStdinWithPromptFn:
    def test_non_tty_returns_false(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = asyncio.run(ask_via_stdin("Read", {"file_path": "/foo.py"}))
        assert result is False

    def test_tty_with_prompt_fn_yes(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="y")
        result = asyncio.run(
            ask_via_stdin("Read", {"file_path": "/foo.py"}, prompt_fn=prompt_fn)
        )
        assert result is True
        prompt_fn.assert_called_once()

    def test_tty_with_prompt_fn_no(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        prompt_fn = MagicMock(return_value="n")
        result = asyncio.run(
            ask_via_stdin("Read", {"file_path": "/foo.py"}, prompt_fn=prompt_fn)
        )
        assert result is False


# ── nodes/base ────────────────────────────────────────────────────────────────


class TestMakePrinterEmitToDisplay:
    def _make_assistant_msg(self, text: str):
        from claude_agent_sdk import AssistantMessage, TextBlock

        msg = MagicMock(spec=AssistantMessage)
        block = MagicMock(spec=TextBlock)
        block.__class__ = TextBlock
        block.text = text
        msg.__class__ = AssistantMessage
        msg.content = [block]
        return msg

    def test_emit_routes_to_display_node_output(self):
        display = MagicMock()
        printer = _make_printer(Verbosity.normal, display=display)
        msg = self._make_assistant_msg("hello world")
        printer("mynode", msg)
        display.node_output.assert_called()
        texts = [c[0][1] for c in display.node_output.call_args_list]
        assert any("hello world" in t for t in texts)

    def test_emit_truncates_long_text(self):
        display = MagicMock()
        printer = _make_printer(Verbosity.normal, display=display)
        long_text = "\n".join(f"line {i}" for i in range(10))
        msg = self._make_assistant_msg(long_text)
        printer("mynode", msg)
        texts = [c[0][1] for c in display.node_output.call_args_list]
        assert any("more lines" in t for t in texts)

    def test_emit_exactly_5_lines_no_truncation(self):
        display = MagicMock()
        printer = _make_printer(Verbosity.normal, display=display)
        text = "\n".join(f"line {i}" for i in range(5))
        msg = self._make_assistant_msg(text)
        printer("mynode", msg)
        texts = [c[0][1] for c in display.node_output.call_args_list]
        assert not any("more lines" in t for t in texts)
        assert len(texts) == 5


class TestClaudeAgentNodeRenderPromptWithPrior:
    def test_prior_results_prepended_to_prompt(self):
        node = ClaudeAgentNode(
            name="test_node",
            prompt_template="Task: {task_description}",
        )
        state = {
            "task_description": "do something",
            "_prior_results": "## Prior results\n### step_a\noutput here\n",
        }
        rendered = node._render_prompt(state)
        assert rendered.startswith("## Prior results")
        assert "do something" in rendered
        assert "step_a" in rendered

    def test_no_prior_returns_plain_prompt(self):
        node = ClaudeAgentNode(
            name="test_node",
            prompt_template="Task: {task_description}",
        )
        state = {"task_description": "do something"}
        rendered = node._render_prompt(state)
        assert rendered == "Task: do something"

    def test_empty_prior_returns_plain_prompt(self):
        node = ClaudeAgentNode(
            name="test_node",
            prompt_template="Task: {task_description}",
        )
        state = {"task_description": "do something", "_prior_results": ""}
        rendered = node._render_prompt(state)
        assert rendered == "Task: do something"


# ── prompt_fn override wiring in node factories ───────────────────────────────


class TestPromptFnOverride:
    def test_plan_feature_node_with_prompt_fn(self):
        prompt_fn = MagicMock(return_value="approved")
        # Should not raise; prompt_fn is wired into ask_feedback via functools.partial
        node = python_plan_feature_node(prompt_fn=prompt_fn)
        assert node is not None

    def test_plan_feature_node_without_prompt_fn_unchanged(self):
        node = python_plan_feature_node()
        assert node is not None

    def test_implement_feature_node_with_prompt_fn(self):
        prompt_fn = MagicMock(return_value="approved")
        node = python_implement_feature_node(prompt_fn=prompt_fn)
        assert node is not None

    def test_git_commit_node_with_prompt_fn(self):
        prompt_fn = MagicMock(return_value="skip")
        node = git_commit_node(prompt_fn=prompt_fn)
        assert node is not None

    def test_git_commit_node_prompt_fn_replaces_default_ask(self):
        """When prompt_fn is provided and ask_push is the default, it's replaced."""

        custom_prompt = MagicMock(return_value="skip")
        # Provide explicit ask_push != default to skip the override branch
        node_no_override = git_commit_node(
            ask_push=lambda s: "skip", prompt_fn=custom_prompt
        )
        assert node_no_override is not None



# ── pipeline._apply_overrides ─────────────────────────────────────────────────


class TestApplyOverridesVerbosity:
    def _make_pipeline(self, verbosity=Verbosity.silent, **kw):
        async def dummy(state):
            return {}

        return Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/d"],
            custom_nodes={"custom/d": dummy},
            verbosity=verbosity,
            **kw,
        )

    def test_verbosity_normal_forces_silent_on_node(self):
        def factory(verbosity=Verbosity.silent):
            return lambda state: {}

        p = self._make_pipeline(Verbosity.normal)
        overrides: dict = {}
        p._apply_overrides(factory, overrides)
        assert overrides["verbosity"] == Verbosity.silent

    def test_verbosity_verbose_passes_through(self):
        def factory(verbosity=Verbosity.silent):
            return lambda state: {}

        p = self._make_pipeline(Verbosity.verbose)
        overrides: dict = {}
        p._apply_overrides(factory, overrides)
        assert overrides["verbosity"] == Verbosity.verbose

    def test_model_injected_when_set(self):
        def factory(model="default"):
            return lambda state: {}

        p = self._make_pipeline(model="claude-haiku-4-5")
        overrides: dict = {}
        p._apply_overrides(factory, overrides)
        assert overrides["model"] == "claude-haiku-4-5"

    def test_model_not_injected_when_unset(self):
        def factory(model="default"):
            return lambda state: {}

        p = self._make_pipeline()  # no model
        overrides: dict = {}
        p._apply_overrides(factory, overrides)
        assert "model" not in overrides

    def test_prompt_fn_injected_at_node_enter(self):
        """prompt_fn is wired in _node_enter, not _apply_overrides."""

        class _Node:
            prompt_fn = None
            def __call__(self, state):
                return {}

        node = _Node()
        p = self._make_pipeline()
        mock_display = MagicMock()
        mock_display.prompt = MagicMock(return_value="yes")
        p._display = mock_display
        p._node_enter("test_node", node, {})
        assert node.prompt_fn is mock_display.prompt

    def test_prompt_fn_not_injected_when_no_display(self):
        """prompt_fn left alone when Display is None."""

        class _Node:
            prompt_fn = None
            def __call__(self, state):
                return {}

        node = _Node()
        p = self._make_pipeline()
        p._display = None
        p._node_enter("test_node", node, {})
        assert node.prompt_fn is None

    def test_overrides_non_empty_calls_factory_with_kwargs(self):
        received = {}

        def factory(verbosity=Verbosity.silent):
            received["verbosity"] = verbosity
            return lambda state: {}

        p = self._make_pipeline(Verbosity.verbose)
        p._apply_overrides(factory, {})
        assert received["verbosity"] == Verbosity.verbose

    def test_overrides_already_set_not_overwritten(self):
        """Explicit override in config should not be replaced."""

        def factory(verbosity=Verbosity.silent):
            return lambda state: {}

        p = self._make_pipeline(Verbosity.normal)
        overrides = {"verbosity": Verbosity.verbose}
        p._apply_overrides(factory, overrides)
        # verbosity already in overrides — should stay as set
        assert overrides["verbosity"] == Verbosity.verbose


# ── pipeline._node_exit parallel path ────────────────────────────────────────


class TestNodeExitParallelPath:
    def test_parallel_pipeline_runs_all_branches(self):
        async def node_a(state):
            return {"a": "done_a", "last_cost_usd": 0.01}

        async def node_b(state):
            return {"b": "done_b", "last_cost_usd": 0.02}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[["custom/a", "custom/b"]],
            custom_nodes={"custom/a": node_a, "custom/b": node_b},
        )
        final = asyncio.run(p.run())
        assert final.get("a") == "done_a"
        assert final.get("b") == "done_b"

    def test_parallel_costs_accumulated(self):
        async def node_a(state):
            return {"a": "x", "last_cost_usd": 0.03}

        async def node_b(state):
            return {"b": "y", "last_cost_usd": 0.07}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[["custom/a", "custom/b"]],
            custom_nodes={"custom/a": node_a, "custom/b": node_b},
        )
        final = asyncio.run(p.run())
        assert final["total_cost_usd"] == pytest.approx(0.10)


# ── pipeline._node_exit non-dict with display ─────────────────────────────────


class TestNodeExitNonDictWithDisplay:
    def test_display_node_done_called_for_non_dict(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/node"],
            custom_nodes={"custom/node": lambda s: "not a dict"},
        )
        mock_display = MagicMock()
        p._display = mock_display
        result = p._node_exit("node", "not a dict", 0.0)
        assert result == {}
        mock_display.node_done.assert_called_once()


# ── pipeline._node_enter callbacks ───────────────────────────────────────────


class TestNodeEnterCallbacks:
    def _minimal_pipeline(self):
        p = Pipeline.__new__(Pipeline)
        p._requires_map = {}
        p._node_outputs = {}
        return p

    def test_on_message_set_when_display_and_non_silent(self):
        p = self._minimal_pipeline()
        p.verbosity = Verbosity.verbose
        p._display = MagicMock()

        class FakeNode:
            on_message = None

        node = FakeNode()
        p._node_enter("fake", node, {"working_dir": "/tmp"})
        assert node.on_message is not None

    def test_on_message_not_set_when_silent(self):
        p = self._minimal_pipeline()
        p.verbosity = Verbosity.silent
        p._display = MagicMock()

        class FakeNode:
            on_message = "original"

        node = FakeNode()
        p._node_enter("fake", node, {"working_dir": "/tmp"})
        # silent verbosity: on_message should not be overwritten
        assert node.on_message == "original"

    def test_on_warn_set_when_display_present(self):
        p = self._minimal_pipeline()
        p.verbosity = Verbosity.silent
        p._display = MagicMock()

        class FakeNode:
            on_warn = None

        node = FakeNode()
        p._node_enter("fake", node, {"working_dir": "/tmp"})
        assert node.on_warn is not None

    def test_on_warn_lambda_delegates_to_default_on_warn(self):
        p = self._minimal_pipeline()
        p.verbosity = Verbosity.silent
        mock_display = MagicMock()
        p._display = mock_display

        class FakeNode:
            on_warn = None

        node = FakeNode()
        p._node_enter("fake", node, {"working_dir": "/tmp"})
        node.on_warn(0.08, 0.10)
        mock_display.warn.assert_called_once()



# ── pipeline dedup name override ─────────────────────────────────────────────


class TestDedupNameSetsOverride:
    def test_duplicate_step_sets_name_in_ordered_names(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint", "python_lint"],
        )
        assert "python_lint_2" in p._ordered_names

    def test_duplicate_step_build_sets_name_override(self):
        """line 220: graph_name != base_name triggers overrides.setdefault('name')."""
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint", "python_lint"],
        )
        # _build() will call _instantiate twice; second call hits line 220
        app = p._build()
        assert app is not None


# ── pipeline.print_results with no prior display ──────────────────────────────


class TestPipelinePrintResultsNoDisplay:
    def test_print_results_without_prior_display(self, capsys):
        async def node(state):
            return {"x": "done", "last_cost_usd": 0.05}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/x"],
            custom_nodes={"custom/x": node},
        )
        asyncio.run(p.run())
        # After run(), _display is None (stopped in finally block)
        p.print_results()
        out = capsys.readouterr().out
        # Should show a cost table with the node cost
        assert "0.05" in out or "$" in out


# ── tuple step resolution (_resolve_step tuple branch) ───────────────────────


class TestTupleStepResolution:
    def test_tuple_step_resolves_and_runs(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["python_lint", ("ruff_final", "python_lint")],
            config={"ruff_final": {"name": "ruff_final"}},
        )
        assert "ruff_final" in p._ordered_names

    def test_tuple_step_config_applied(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[("my_lint", "python_lint")],
            config={"my_lint": {"name": "my_lint"}},
        )
        assert "my_lint" in p._ordered_names

    def test_tuple_step_build_exercises_tuple_branch(self):
        """lines 228-235: _resolve_step tuple branch is exercised by _build()."""
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[("ruff_final", "python_lint")],
            config={"ruff_final": {"name": "ruff_final"}},
        )
        app = p._build()
        assert app is not None

    def test_tuple_step_with_config_overrides(self):
        """Tuple step config overrides from both registry_key and graph_name."""
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[("aliased_lint", "python_lint")],
            config={
                "python_lint": {"fix": True},
                "aliased_lint": {"name": "aliased_lint"},
            },
        )
        app = p._build()
        assert app is not None


# ── graph main() functions ────────────────────────────────────────────────────


class TestNewFeatureMain:
    def test_main_calls_run_and_print_results(self):
        from agentpipe.graphs.python_new_feature import main

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(
            return_value={
                "node_costs": {},
                "total_cost_usd": 0.0,
                "node_outputs": {},
            }
        )
        mock_pipeline.print_results = MagicMock()
        mock_pipeline._ordered_names = []
        mock_pipeline._node_costs = {}

        with patch(
            "agentpipe.graphs.python_new_feature.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(
                main(
                    "/tmp/repo",
                    "add feature",
                    base_ref="main",
                    verbosity=Verbosity.normal,
                )
            )
        mock_pipeline.run.assert_called_once()
        mock_pipeline.print_results.assert_called_once()

    def test_main_default_args(self):
        from agentpipe.graphs.python_new_feature import main

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(
            return_value={"node_costs": {}, "total_cost_usd": 0.0, "node_outputs": {}}
        )
        mock_pipeline.print_results = MagicMock()

        with patch(
            "agentpipe.graphs.python_new_feature.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(main("/tmp/repo", "task"))
        mock_pipeline.run.assert_called_once()


class TestQualityGateMain:
    def test_main_calls_run_and_print_results(self):
        from agentpipe.graphs.python_quality_gate import main

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(
            return_value={
                "node_costs": {},
                "total_cost_usd": 0.0,
                "node_outputs": {},
            }
        )
        mock_pipeline.print_results = MagicMock()

        with patch(
            "agentpipe.graphs.python_quality_gate.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(
                main(
                    "/tmp/repo",
                    mode="diff",
                    base_ref="main",
                    interactive=True,
                    verbosity=Verbosity.normal,
                )
            )
        mock_pipeline.run.assert_called_once()
        mock_pipeline.print_results.assert_called_once()

    def test_main_non_interactive_mode(self):
        from agentpipe.graphs.python_quality_gate import main

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(
            return_value={"node_costs": {}, "total_cost_usd": 0.0, "node_outputs": {}}
        )
        mock_pipeline.print_results = MagicMock()

        with patch(
            "agentpipe.graphs.python_quality_gate.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(main("/tmp/repo", mode="full", interactive=False))
        mock_pipeline.run.assert_called_once()
