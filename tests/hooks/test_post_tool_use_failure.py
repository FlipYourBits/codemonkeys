"""Tests for PostToolUseFailure hook — log failed tool calls to JSONL."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "post_tool_use_failure.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestFailureLogging:
    def test_creates_log_entry(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_response": "permission denied",
            "session_id": "sess-fail-1",
        }
        result = run_hook(data)
        assert result.returncode == 0

        log_file = tmp_path / ".codemonkeys" / "logs" / "failures.jsonl"
        assert log_file.exists()

        record = json.loads(log_file.read_text().strip())
        assert record["tool"] == "Bash"
        assert record["input"] == {"command": "rm -rf /"}
        assert record["error"] == "permission denied"
        assert record["session_id"] == "sess-fail-1"
        assert "timestamp" in record

    def test_appends_to_existing_log(self, tmp_path):
        log_dir = tmp_path / ".codemonkeys" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "failures.jsonl"
        log_file.write_text('{"existing": true}\n')

        data = {
            "cwd": str(tmp_path),
            "tool_name": "Edit",
            "tool_input": {"file_path": "x.py"},
            "error": "file not found",
            "session_id": "sess-2",
        }
        run_hook(data)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["tool"] == "Edit"

    def test_defaults_for_missing_fields(self, tmp_path):
        data = {"cwd": str(tmp_path)}
        result = run_hook(data)
        assert result.returncode == 0

        log_file = tmp_path / ".codemonkeys" / "logs" / "failures.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["tool"] == "unknown"
        assert record["error"] == "unknown"
        assert record["session_id"] == "unknown"

    def test_creates_logs_directory(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "tool_name": "Write",
            "tool_response": "some error",
        }
        run_hook(data)

        assert (tmp_path / ".codemonkeys" / "logs").is_dir()
