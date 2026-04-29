"""Unit tests for base.py pure functions, ClaudeAgentNode construction, and ShellNode."""

from __future__ import annotations

import asyncio
import subprocess
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from codemonkeys.nodes.base import (
    ClaudeAgentNode,
    ShellNode,
    Verbosity,
    _compose_system_prompt,
    _format_usage,
    _make_printer,
)


# ---------- _format_usage ----------


class TestFormatUsage:
    def test_none_returns_empty(self):
        assert _format_usage(None) == ""

    def test_empty_dict_returns_empty(self):
        assert _format_usage({}) == ""

    def test_input_output_tokens(self):
        result = _format_usage({"input_tokens": 100, "output_tokens": 50})
        assert "in=100" in result
        assert "out=50" in result

    def test_cache_read(self):
        result = _format_usage({"input_tokens": 10, "cache_read_input_tokens": 500})
        assert "cache_read=500" in result

    def test_cache_create(self):
        result = _format_usage({"input_tokens": 10, "cache_creation_input_tokens": 200})
        assert "cache_create=200" in result

    def test_none_tokens_empty_when_both_none(self):
        # Both None -> condition `in_tok is not None or out_tok is not None` is False
        result = _format_usage({"input_tokens": None, "output_tokens": None})
        assert result == ""

    def test_zero_input_tokens_still_shows(self):
        result = _format_usage({"input_tokens": 0, "output_tokens": 5})
        assert "in=0" in result
        assert "out=5" in result

    def test_only_in_tokens(self):
        result = _format_usage({"input_tokens": 42})
        assert "in=42" in result
        assert "out=0" in result

    def test_all_fields(self):
        result = _format_usage(
            {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 40,
            }
        )
        assert "in=10" in result
        assert "out=20" in result
        assert "cache_read=30" in result
        assert "cache_create=40" in result


# ---------- _make_printer ----------


class TestMakePrinter:
    def test_silent_returns_none(self):
        assert _make_printer(Verbosity.silent) is None

    def test_normal_returns_callable(self):
        printer = _make_printer(Verbosity.normal)
        assert callable(printer)

    def test_verbose_returns_callable(self):
        printer = _make_printer(Verbosity.verbose)
        assert callable(printer)

    def test_normal_prints_text_block(self, capsys):
        from claude_agent_sdk import AssistantMessage, TextBlock

        printer = _make_printer(Verbosity.normal)
        msg = MagicMock(spec=AssistantMessage)
        msg.content = [MagicMock(spec=TextBlock, text="hello world")]
        # Make isinstance checks work
        msg.__class__ = AssistantMessage
        msg.content[0].__class__ = TextBlock
        printer("mynode", msg)
        captured = capsys.readouterr()
        assert "[mynode]" in captured.err
        assert "hello world" in captured.err

    def test_normal_prints_tool_use(self, capsys):
        from claude_agent_sdk import AssistantMessage, ToolUseBlock

        printer = _make_printer(Verbosity.normal)
        msg = MagicMock(spec=AssistantMessage)
        tool_block = MagicMock(spec=ToolUseBlock)
        tool_block.__class__ = ToolUseBlock
        tool_block.name = "Read"
        tool_block.input = {"file_path": "/foo.py"}
        msg.__class__ = AssistantMessage
        msg.content = [tool_block]
        printer("n", msg)
        captured = capsys.readouterr()
        assert "Read" in captured.err

    def test_normal_prints_thinking(self, capsys):
        from claude_agent_sdk import AssistantMessage, ThinkingBlock

        printer = _make_printer(Verbosity.normal)
        msg = MagicMock(spec=AssistantMessage)
        block = MagicMock(spec=ThinkingBlock)
        block.__class__ = ThinkingBlock
        msg.__class__ = AssistantMessage
        msg.content = [block]
        printer("n", msg)
        captured = capsys.readouterr()
        assert "thinking" in captured.err

    def test_normal_result_message(self, capsys):
        from claude_agent_sdk import ResultMessage

        printer = _make_printer(Verbosity.normal)
        msg = MagicMock(spec=ResultMessage)
        msg.__class__ = ResultMessage
        printer("n", msg)
        captured = capsys.readouterr()
        assert "done" in captured.err

    def test_verbose_result_message_with_cost(self, capsys):
        from claude_agent_sdk import ResultMessage

        printer = _make_printer(Verbosity.verbose)
        msg = MagicMock(spec=ResultMessage)
        msg.__class__ = ResultMessage
        msg.total_cost_usd = 0.1234
        msg.usage = {"input_tokens": 100, "output_tokens": 50}
        printer("n", msg)
        captured = capsys.readouterr()
        assert "cost=$0.1234" in captured.err
        assert "in=100" in captured.err

    def test_verbose_assistant_message_with_usage(self, capsys):
        from claude_agent_sdk import AssistantMessage, TextBlock

        printer = _make_printer(Verbosity.verbose)
        msg = MagicMock(spec=AssistantMessage)
        msg.__class__ = AssistantMessage
        msg.usage = {"input_tokens": 10, "output_tokens": 5}
        block = MagicMock(spec=TextBlock, text="hi")
        block.__class__ = TextBlock
        msg.content = [block]
        printer("n", msg)
        captured = capsys.readouterr()
        assert "in=10" in captured.err


# ---------- _compose_system_prompt ----------


class TestComposeSystemPrompt:
    def test_no_skills_returns_base(self):
        assert _compose_system_prompt("base prompt", []) == "base prompt"

    def test_string_skill_appended(self):
        result = _compose_system_prompt("base", ["guideline one"])
        assert "base" in result
        assert "guideline one" in result
        assert "Operating guidelines" in result

    def test_path_skill_read(self, tmp_path):
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("file skill content")
        result = _compose_system_prompt("base", [skill_file])
        assert "file skill content" in result

    def test_mixed_skills(self, tmp_path):
        skill_file = tmp_path / "s.md"
        skill_file.write_text("from file")
        result = _compose_system_prompt("base", ["inline", skill_file])
        assert "inline" in result
        assert "from file" in result


# ---------- ClaudeAgentNode construction ----------


class TestClaudeAgentNodeConstruction:
    def test_basic_construction(self):
        node = ClaudeAgentNode(name="test")
        assert node.name == "test"
        assert node.declared_outputs == ("test", "last_cost_usd")

    def test_resolve_warn_pcts_hard_cap_passthrough(self):
        result = ClaudeAgentNode._resolve_warn_pcts(0.8, hard_cap=True)
        assert result == 0.8

    def test_resolve_warn_pcts_soft_cap_none_adds_1(self):
        result = ClaudeAgentNode._resolve_warn_pcts(None, hard_cap=False)
        assert result == [1.0]

    def test_resolve_warn_pcts_soft_cap_adds_1_if_missing(self):
        result = ClaudeAgentNode._resolve_warn_pcts(0.8, hard_cap=False)
        assert 1.0 in result
        assert 0.8 in result

    def test_resolve_warn_pcts_soft_cap_no_dup_1(self):
        result = ClaudeAgentNode._resolve_warn_pcts([0.8, 1.0], hard_cap=False)
        assert result.count(1.0) == 1

    def test_resolve_warn_pcts_list_soft_cap(self):
        result = ClaudeAgentNode._resolve_warn_pcts([0.5, 0.9], hard_cap=False)
        assert 1.0 in result

    def test_render_prompt_basic(self):
        node = ClaudeAgentNode(name="t", prompt_template="Task: {task_description}")
        rendered = node._render_prompt({"task_description": "do stuff"})
        assert rendered == "Task: do stuff"

    def test_render_prompt_missing_key_raises(self):
        node = ClaudeAgentNode(name="t", prompt_template="{missing_key}")
        with pytest.raises(KeyError, match="missing_key"):
            node._render_prompt({"other": "val"})

    def test_build_options_with_cwd(self):
        node = ClaudeAgentNode(name="t", model="sonnet")
        opts = node._build_options("/tmp/repo")
        assert opts.cwd == "/tmp/repo"
        assert opts.model == "sonnet"

    def test_build_options_no_cwd(self):
        node = ClaudeAgentNode(name="t")
        opts = node._build_options(None)
        assert not hasattr(opts, "cwd") or opts.cwd is None

    def test_build_options_max_turns(self):
        node = ClaudeAgentNode(name="t", max_turns=5)
        opts = node._build_options(None)
        assert opts.max_turns == 5

    def test_build_options_hard_cap_budget(self):
        node = ClaudeAgentNode(name="t", max_budget_usd=2.0, hard_cap=True)
        opts = node._build_options(None)
        assert opts.max_budget_usd == 2.0

    def test_build_options_soft_cap_no_sdk_budget(self):
        node = ClaudeAgentNode(name="t", max_budget_usd=2.0, hard_cap=False)
        opts = node._build_options(None)
        assert not hasattr(opts, "max_budget_usd") or opts.max_budget_usd is None

    def test_build_options_extra_options(self):
        node = ClaudeAgentNode(name="t", extra_options={"max_turns": 3})
        opts = node._build_options(None)
        assert opts.max_turns == 3


# ---------- ShellNode ----------


class TestShellNode:
    def test_resolve_string_command(self):
        node = ShellNode(name="t", command="echo hello world")
        assert node._resolve({}) == ["echo", "hello", "world"]

    def test_resolve_list_command(self):
        node = ShellNode(name="t", command=["echo", "hi"])
        assert node._resolve({}) == ["echo", "hi"]

    def test_resolve_callable_command(self):
        node = ShellNode(name="t", command=lambda s: f"echo {s['msg']}")
        assert node._resolve({"msg": "hi"}) == ["echo", "hi"]

    def test_callable_returns_list(self):
        node = ShellNode(name="t", command=lambda s: ["echo", s["msg"]])
        assert node._resolve({"msg": "hi"}) == ["echo", "hi"]

    def test_silent_run(self):
        node = ShellNode(name="t", command="echo hello")
        result = asyncio.run(node({"working_dir": None}))
        assert result["t"] == "hello"

    def test_check_failure_raises(self):
        node = ShellNode(name="t", command="false", check=True)
        with pytest.raises(subprocess.CalledProcessError):
            asyncio.run(node({"working_dir": None}))

    def test_no_check_captures_output(self):
        node = ShellNode(name="t", command="echo ok && exit 1", check=False)
        # The command runs as a list from shlex so this won't work as expected
        # Test with a simple false command
        node2 = ShellNode(name="t", command="false", check=False)
        result = asyncio.run(node2({"working_dir": None}))
        assert result["t"] == ""

    def test_declared_outputs(self):
        node = ShellNode(name="myshell", command="true")
        assert node.declared_outputs == ("myshell",)

    def test_streaming_run(self):
        node = ShellNode(name="t", command="echo streaming_test")
        lines: list[str] = []
        node.on_output = lambda name, line: lines.append(line)
        result = asyncio.run(node({"working_dir": None}))
        assert "streaming_test" in result["t"]
        assert any("streaming_test" in l for l in lines)

    def test_streaming_check_failure(self):
        node = ShellNode(name="t", command="false", check=True)
        node.on_output = lambda name, line: None
        with pytest.raises(subprocess.CalledProcessError):
            asyncio.run(node({"working_dir": None}))

    def test_streaming_timeout(self):
        node = ShellNode(name="t", command="sleep 60", timeout=0.1)
        node.on_output = lambda name, line: None
        with pytest.raises(subprocess.TimeoutExpired):
            asyncio.run(node({"working_dir": None}))


# ---------- ClaudeAgentNode output= ----------


class TestClaudeAgentNodeOutput:
    def test_output_appends_instructions_to_system_prompt(self):
        class MyOutput(BaseModel):
            value: int = Field(examples=[42])

        node = ClaudeAgentNode(name="t", output=MyOutput)
        assert "## Output" in node.system_prompt
        assert "42" in node.system_prompt

    def test_no_output_leaves_system_prompt_unchanged(self):
        node = ClaudeAgentNode(name="t", system_prompt="base")
        assert "## Output" not in node.system_prompt
        assert node.system_prompt == "base"

    def test_output_cls_stored(self):
        class MyOutput(BaseModel):
            x: int

        node = ClaudeAgentNode(name="t", output=MyOutput)
        assert node.output_cls is MyOutput

    def test_no_output_cls_is_none(self):
        node = ClaudeAgentNode(name="t")
        assert node.output_cls is None


class TestShellNodeOutput:
    def test_output_parses_json_stdout(self):
        class MyOutput(BaseModel):
            value: int

        node = ShellNode(name="t", command="echo '{\"value\": 42}'", output=MyOutput)
        result = asyncio.run(node({"working_dir": None}))
        assert hasattr(result["t"], "value")
        assert result["t"].value == 42

    def test_no_output_returns_raw_string(self):
        node = ShellNode(name="t", command="echo hello")
        result = asyncio.run(node({"working_dir": None}))
        assert result["t"] == "hello"

    def test_output_cls_stored(self):
        class MyOutput(BaseModel):
            x: int

        node = ShellNode(name="t", command="true", output=MyOutput)
        assert node.output_cls is MyOutput

    def test_no_output_cls_is_none(self):
        node = ShellNode(name="t", command="true")
        assert node.output_cls is None
