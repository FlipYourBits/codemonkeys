"""Tests for SubagentStop hook — log completion and verify tests for python-implementer."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "subagent_stop.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestLogging:
    def test_writes_jsonl_record(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-789",
            "agent_name": "python-implementer",
        }
        run_hook(data)

        log_file = tmp_path / ".codemonkeys" / "logs" / "subagents.jsonl"
        assert log_file.exists()

        record = json.loads(log_file.read_text().strip())
        assert record["event"] == "stop"
        assert record["session_id"] == "sess-789"
        assert record["agent_name"] == "python-implementer"
        assert "timestamp" in record

    def test_appends_to_existing_log(self, tmp_path):
        log_dir = tmp_path / ".codemonkeys" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "subagents.jsonl"
        log_file.write_text('{"event": "start", "existing": true}\n')

        data = {"cwd": str(tmp_path), "session_id": "s1", "agent_name": "agent-b"}
        run_hook(data)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["existing"] is True
        assert json.loads(lines[1])["event"] == "stop"

    def test_defaults_for_missing_fields(self, tmp_path):
        data = {"cwd": str(tmp_path)}
        result = run_hook(data)
        assert result.returncode == 0

        log_file = tmp_path / ".codemonkeys" / "logs" / "subagents.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["session_id"] == "unknown"
        assert record["agent_name"] == "unknown"


class TestNonVerifiedAgents:
    def test_non_verified_agent_passes_through(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-abc",
            "agent_name": "code-reviewer",
        }
        result = run_hook(data)
        assert result.returncode == 0
        assert "[codemonkeys] subagent completed: code-reviewer" in result.stdout

    def test_unknown_agent_passes_through(self, tmp_path):
        data = {"cwd": str(tmp_path), "agent_name": "some-other-agent"}
        result = run_hook(data)
        assert result.returncode == 0
        assert "some-other-agent" in result.stdout


class TestPythonImplementerVerification:
    def test_passes_when_tests_pass(self, tmp_path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_ok(): assert True\n")

        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-ok",
            "agent_name": "python-implementer",
        }
        result = run_hook(data)
        assert result.returncode == 0
        assert "tests passed" in result.stdout

    def test_blocks_when_tests_fail(self, tmp_path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_bad(): assert False\n")

        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-fail",
            "agent_name": "python-implementer",
        }
        result = run_hook(data)
        assert result.returncode == 2
        assert "tests are failing" in result.stderr

    def test_still_logs_when_blocking(self, tmp_path):
        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_bad(): assert False\n")

        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-log",
            "agent_name": "python-implementer",
        }
        run_hook(data)

        log_file = tmp_path / ".codemonkeys" / "logs" / "subagents.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["agent_name"] == "python-implementer"
        assert record["event"] == "stop"

    def test_passes_when_no_tests_found(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-empty",
            "agent_name": "python-implementer",
        }
        result = run_hook(data)
        assert result.returncode == 0
