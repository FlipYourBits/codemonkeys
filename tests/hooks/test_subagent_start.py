"""Tests for SubagentStart hook — log sub-agent spawn events."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "subagent_start.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestSubagentStart:
    def test_writes_jsonl_record(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-123",
            "agent_name": "python-implementer",
        }
        result = run_hook(data)
        assert result.returncode == 0

        log_file = tmp_path / ".codemonkeys" / "logs" / "subagents.jsonl"
        assert log_file.exists()

        record = json.loads(log_file.read_text().strip())
        assert record["event"] == "start"
        assert record["session_id"] == "sess-123"
        assert record["agent_name"] == "python-implementer"
        assert "timestamp" in record

    def test_prints_status_line(self, tmp_path):
        data = {
            "cwd": str(tmp_path),
            "session_id": "sess-456",
            "agent_name": "code-reviewer",
        }
        result = run_hook(data)
        assert "[codemonkeys] subagent started: code-reviewer" in result.stdout

    def test_appends_to_existing_log(self, tmp_path):
        log_dir = tmp_path / ".codemonkeys" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "subagents.jsonl"
        log_file.write_text('{"event": "stop", "existing": true}\n')

        data = {"cwd": str(tmp_path), "session_id": "s1", "agent_name": "agent-a"}
        run_hook(data)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["existing"] is True
        assert json.loads(lines[1])["event"] == "start"

    def test_defaults_for_missing_fields(self, tmp_path):
        data = {"cwd": str(tmp_path)}
        result = run_hook(data)
        assert result.returncode == 0

        log_file = tmp_path / ".codemonkeys" / "logs" / "subagents.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["session_id"] == "unknown"
        assert record["agent_name"] == "unknown"
