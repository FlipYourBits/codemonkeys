# tests/test_log_metrics.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codemonkeys.core.log_metrics import extract_metrics


def _write_log(tmp_path: Path, lines: list[dict]) -> Path:
    """Write JSONL lines to a temp log file and a companion .md file."""
    log_file = tmp_path / "test_agent_2026-01-01_00-00-00.log"
    log_file.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    md_file = tmp_path / "test_agent_2026-01-01_00-00-00.md"
    md_file.write_text(
        "# Agent: test_agent\n\n**Model:** sonnet\n**Tools:** Read, Grep\n\n"
        "## System Prompt\n\n```\nYou review files.\n```\n\n"
        "## User Prompt\n\n```\nReview foo.py\n```\n\n"
        "## Structured Output\n\n```json\n{}\n```\n"
    )
    return log_file


MINIMAL_LOG = [
    {
        "event": "agent_start",
        "name": "test_agent",
        "model": "sonnet",
        "tools": ["Read", "Grep"],
        "prompt_length": 100,
        "user_prompt": "Review foo.py",
        "ts": "2026-01-01T00:00:00+00:00",
    },
    {
        "type": "SystemMessage",
        "ts": "2026-01-01T00:00:01+00:00",
    },
    {
        "type": "AssistantMessage",
        "usage": {
            "input_tokens": 500,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "content": [
            {"type": "thinking", "thinking": "Let me read the file."},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}},
        ],
        "ts": "2026-01-01T00:00:02+00:00",
    },
    {
        "type": "UserMessage",
        "ts": "2026-01-01T00:00:03+00:00",
    },
    {
        "type": "AssistantMessage",
        "usage": {
            "input_tokens": 800,
            "output_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 400,
        },
        "content": [
            {"type": "thinking", "thinking": "The file looks good."},
            {"type": "text", "text": "Review complete."},
        ],
        "ts": "2026-01-01T00:00:04+00:00",
    },
    {
        "type": "ResultMessage",
        "result": "Review complete.",
        "usage": {"input_tokens": 1300, "output_tokens": 150},
        "cost": 0.01,
        "duration_ms": 4000,
        "ts": "2026-01-01T00:00:05+00:00",
    },
]


class TestExtractMetrics:
    def test_extracts_agent_metadata(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.agent_name == "test_agent"
        assert metrics.model == "sonnet"
        assert metrics.allowed_tools == ["Read", "Grep"]
        assert metrics.user_prompt == "Review foo.py"

    def test_extracts_system_prompt_from_md(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert "You review files." in metrics.system_prompt

    def test_counts_assistant_turns(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert len(assistant_turns) == 2

    def test_extracts_tool_calls(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert len(metrics.tool_calls) == 1
        assert metrics.tool_calls[0].name == "Read"
        assert "foo.py" in metrics.tool_calls[0].args_summary

    def test_extracts_thinking_content(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert "Let me read the file." in assistant_turns[0].thinking_content

    def test_extracts_token_usage(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.total_input_tokens == 1300
        assert metrics.total_output_tokens == 150

    def test_extracts_cache_tokens(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assistant_turns = [t for t in metrics.turns if t.role == "assistant"]
        assert assistant_turns[1].cache_read_tokens == 400

    def test_extracts_cost_and_duration(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.total_cost == 0.01
        assert metrics.duration_ms == 4000

    def test_extracts_structured_output(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        assert metrics.structured_output == "Review complete."


class TestRepeatedToolCalls:
    def test_detects_repeated_tool_calls(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "foo.py"},
                    },
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "foo.py"},
                    },
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.repeated_tool_calls) >= 1
        assert metrics.repeated_tool_calls[0].name == "Read"

    def test_no_false_positives_for_different_args(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "foo.py"},
                    },
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "bar.py"},
                    },
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.repeated_tool_calls) == 0


class TestUnauthorizedToolCalls:
    def test_detects_unauthorized_tool(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.unauthorized_tool_calls) == 1
        assert metrics.unauthorized_tool_calls[0].name == "Bash"

    def test_bash_pattern_matching(self, tmp_path):
        log_lines = [
            {
                "event": "agent_start",
                "name": "test_agent",
                "model": "haiku",
                "tools": ["Read", "Bash(git log*)"],
                "prompt_length": 100,
                "user_prompt": "Check history",
                "ts": "2026-01-01T00:00:00+00:00",
            },
            {"type": "SystemMessage", "ts": "2026-01-01T00:00:01+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git log --oneline -5"},
                    },
                ],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:03+00:00"},
            {
                "type": "AssistantMessage",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    },
                ],
                "ts": "2026-01-01T00:00:04+00:00",
            },
            {"type": "UserMessage", "ts": "2026-01-01T00:00:05+00:00"},
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.unauthorized_tool_calls) == 1
        assert "ls" in metrics.unauthorized_tool_calls[0].args_summary


class TestRateLimitEvents:
    def test_captures_rate_limit_events(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "type": "RateLimitEvent",
                "status": "allowed",
                "rate_limit_type": "five_hour",
                "resets_at": 1778101800,
                "utilization": None,
                "ts": "2026-01-01T00:00:01+00:00",
            },
            MINIMAL_LOG[2],
            MINIMAL_LOG[3],
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.rate_limit_events) == 1
        assert metrics.rate_limit_events[0]["status"] == "allowed"


class TestToolDeniedEvents:
    def test_captures_tool_denied(self, tmp_path):
        log_lines = [
            MINIMAL_LOG[0],
            MINIMAL_LOG[1],
            {
                "event": "tool_denied",
                "tool": "Bash",
                "command": "rm -rf /",
                "permitted_patterns": ["git log*"],
                "ts": "2026-01-01T00:00:02+00:00",
            },
            MINIMAL_LOG[-1],
        ]
        log_file = _write_log(tmp_path, log_lines)
        metrics = extract_metrics(log_file)
        assert len(metrics.unauthorized_tool_calls) == 1
        assert "rm -rf" in metrics.unauthorized_tool_calls[0].args_summary


class TestSerialization:
    def test_to_json_roundtrips(self, tmp_path):
        log_file = _write_log(tmp_path, MINIMAL_LOG)
        metrics = extract_metrics(log_file)
        json_str = metrics.to_json()
        data = json.loads(json_str)
        assert data["agent_name"] == "test_agent"
        assert isinstance(data["turns"], list)
        assert isinstance(data["tool_calls"], list)


class TestRealLogExtraction:
    """Smoke test against actual log files if they exist."""

    def test_extract_from_real_log_if_available(self):
        log_dir = Path(".codemonkeys/logs")
        if not log_dir.exists():
            pytest.skip("No .codemonkeys/logs directory")
        log_files = sorted(log_dir.rglob("*.log"))
        if not log_files:
            pytest.skip("No log files found")

        metrics = extract_metrics(log_files[0])
        assert metrics.agent_name
        assert metrics.model
        assert metrics.total_turns > 0
        assert len(metrics.turns) > 0
        json_str = metrics.to_json()
        data = json.loads(json_str)
        assert data["agent_name"] == metrics.agent_name


class TestRunAgentAuditFlag:
    def test_audit_flag_is_accepted(self):
        import codemonkeys.run_agent as ra

        parser = ra._build_parser()
        args = parser.parse_args(["changelog_reviewer", "--audit"])
        assert args.audit is True

    def test_no_audit_by_default(self):
        import codemonkeys.run_agent as ra

        parser = ra._build_parser()
        args = parser.parse_args(["changelog_reviewer"])
        assert args.audit is False
