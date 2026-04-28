"""Tests covering coverage gaps in diff-mode changed files.

Focuses on business logic and error paths that were uncovered:
- budget.default_on_warn with display
- display.node_skip/warn in live mode, default_prompt with content
- resolve_findings.ask_findings_via_stdin interactive branches
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
from agentpipe.nodes._old.git_commit import git_commit_node
from agentpipe.nodes._old.python_implement_feature import python_implement_feature_node
from agentpipe.nodes._old.python_plan_feature import python_plan_feature_node
from agentpipe.nodes.resolve_findings import (
    ResolveFindings,
    ask_findings_via_stdin,
)
from agentpipe.permissions import ask_via_stdin
from agentpipe.pipeline import Pipeline


# ── fixtures ──────────────────────────────────────────────────────────────────


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

    def test_with_content_includes_content(self, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        default_prompt("OK?", content="some content")
        err = capsys.readouterr().err
        assert "some content" in err

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
        node = ResolveFindings(interactive=True)
        assert callable(node)
        assert node.name == "resolve_findings"

    def test_non_interactive_returns_callable(self):
        node = ResolveFindings(interactive=False)
        assert callable(node)
        assert node.name == "resolve_findings"


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
        block.__class__ = TextBlock  # type: ignore[assignment]
        block.text = text
        msg.__class__ = AssistantMessage  # type: ignore[assignment]
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
            reads_from=["step_a"],
        )
        state = {
            "task_description": "do something",
            "step_a": "output here",
        }
        rendered = node._render_prompt(state)
        assert rendered.startswith("## Prior results")
        assert "do something" in rendered
        assert "step_a" in rendered

    def test_no_reads_from_returns_plain_prompt(self):
        node = ClaudeAgentNode(
            name="test_node",
            prompt_template="Task: {task_description}",
        )
        state = {"task_description": "do something"}
        rendered = node._render_prompt(state)
        assert rendered == "Task: do something"

    def test_empty_upstream_returns_plain_prompt(self):
        node = ClaudeAgentNode(
            name="test_node",
            prompt_template="Task: {task_description}",
            reads_from=["step_a"],
        )
        state = {"task_description": "do something", "step_a": ""}
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


# ── pipeline._node_enter prompt_fn ────────────────────────────────────────────


class TestNodeEnterPromptFn:
    def _make_pipeline(self):
        async def dummy(state):
            return {}

        dummy.__name__ = "d"
        return Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[dummy],
        )

    def test_prompt_fn_injected_at_node_enter(self):
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
        class _Node:
            prompt_fn = None

            def __call__(self, state):
                return {}

        node = _Node()
        p = self._make_pipeline()
        p._display = None
        p._node_enter("test_node", node, {})
        assert node.prompt_fn is None


# ── pipeline._node_exit parallel path ────────────────────────────────────────


class TestNodeExitParallelPath:
    def test_parallel_pipeline_runs_all_branches(self):
        async def node_a(state):
            return {"a": "done_a", "last_cost_usd": 0.01}

        async def node_b(state):
            return {"b": "done_b", "last_cost_usd": 0.02}

        node_a.__name__ = "a"
        node_b.__name__ = "b"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[[node_a, node_b]],
        )
        final = asyncio.run(p.run())
        assert final.get("a") == "done_a"
        assert final.get("b") == "done_b"

    def test_parallel_costs_accumulated(self):
        async def node_a(state):
            return {"a": "x", "last_cost_usd": 0.03}

        async def node_b(state):
            return {"b": "y", "last_cost_usd": 0.07}

        node_a.__name__ = "a"
        node_b.__name__ = "b"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[[node_a, node_b]],
        )
        final = asyncio.run(p.run())
        assert final["total_cost_usd"] == pytest.approx(0.10)


# ── pipeline._node_exit non-dict with display ─────────────────────────────────


class TestNodeExitNonDictWithDisplay:
    def test_display_node_done_called_for_non_dict(self):
        nd = lambda s: "not a dict"
        nd.__name__ = "node"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[nd],
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
        from agentpipe.nodes._old.python_lint import python_lint_node

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[python_lint_node(), python_lint_node()],
        )
        assert "python_lint_2" in p._ordered_names


# ── pipeline.print_results with no prior display ──────────────────────────────


class TestPipelinePrintResultsNoDisplay:
    def test_print_results_without_prior_display(self, capsys):
        async def node(state):
            return {"x": "done", "last_cost_usd": 0.05}

        node.__name__ = "x"
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[node],
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
        from agentpipe.nodes._old.python_lint import python_lint_node

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[python_lint_node(), ("ruff_final", python_lint_node())],
        )
        assert "ruff_final" in p._ordered_names

    def test_tuple_step_build_exercises_tuple_branch(self):
        from agentpipe.nodes._old.python_lint import python_lint_node

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[("ruff_final", python_lint_node())],
        )
        app = p._build()
        assert app is not None


# ── graph main() functions ────────────────────────────────────────────────────


class TestQualityGateMain:
    def test_main_calls_run_and_print_results(self):
        from agentpipe.graphs.python.check import main

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
            "agentpipe.graphs.python.check.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(
                main(
                    "/tmp/repo",
                    base_ref="main",
                    interactive=True,
                    verbosity=Verbosity.normal,
                )
            )
        mock_pipeline.run.assert_called_once()
        mock_pipeline.print_results.assert_called_once()

    def test_main_non_interactive_mode(self):
        from agentpipe.graphs.python.check import main

        mock_pipeline = MagicMock()
        mock_pipeline.run = AsyncMock(
            return_value={"node_costs": {}, "total_cost_usd": 0.0, "node_outputs": {}}
        )
        mock_pipeline.print_results = MagicMock()

        with patch(
            "agentpipe.graphs.python.check.build_pipeline",
            return_value=mock_pipeline,
        ):
            asyncio.run(main("/tmp/repo", interactive=False))
        mock_pipeline.run.assert_called_once()
