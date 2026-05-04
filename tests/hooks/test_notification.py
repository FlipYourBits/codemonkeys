"""Tests for Notification hook — desktop alerts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

HOOK_PATH = Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "notification.py"
HOOK = str(HOOK_PATH)


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestNotification:
    def test_exits_cleanly(self):
        result = run_hook({"message": "Claude is waiting for your input"})
        assert result.returncode == 0

    def test_handles_missing_message(self):
        result = run_hook({})
        assert result.returncode == 0

    def test_subprocess_called_with_correct_args(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("notification", HOOK_PATH)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)

        with patch("subprocess.run") as mock_run:
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps({"message": "test message"})
                assert spec.loader is not None
                spec.loader.exec_module(mod)
                mod.main()

        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[0] == "notify-send"
        assert "--app-name=Claude Code" in cmd
        assert "Claude Code" in cmd
        assert "test message" in cmd

    def test_graceful_on_missing_notify_send(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("notification_missing", HOOK_PATH)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps({"message": "test"})
                assert spec.loader is not None
                spec.loader.exec_module(mod)
                mod.main()
