"""Tests for PreToolUse hook — destructive commands and .env protection."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "pre_tool_use.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestDestructiveCommands:
    def test_rm_rf_blocked(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/stuff"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_git_force_push_blocked(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_git_reset_hard_blocked(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_safe_command_allowed(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "."})
        assert result.stdout.strip() == ""
        assert result.returncode == 0


class TestEnvFileProtection:
    def test_read_env_blocked(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": "/project/.env"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert ".env" in output["hookSpecificOutput"]["permissionDecisionReason"]

    def test_edit_env_blocked(self):
        result = run_hook({"tool_name": "Edit", "tool_input": {"file_path": ".env"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_write_env_blocked(self):
        result = run_hook({"tool_name": "Write", "tool_input": {"file_path": "/home/user/project/.env"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_env_local_blocked(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".env.local"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_env_sample_allowed(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".env.sample"}, "cwd": "."})
        assert result.stdout.strip() == ""
        assert result.returncode == 0

    def test_env_example_allowed(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".env.example"}, "cwd": "."})
        assert result.stdout.strip() == ""
        assert result.returncode == 0

    def test_env_template_allowed(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".env.template"}, "cwd": "."})
        assert result.stdout.strip() == ""
        assert result.returncode == 0

    def test_bash_cat_env_blocked(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "cat .env"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_bash_source_env_blocked(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "source .env"}, "cwd": "."})
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_bash_cat_env_sample_allowed(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "cat .env.sample"}, "cwd": "."})
        assert result.returncode == 0
        # Should not contain a deny decision
        if result.stdout.strip():
            output = json.loads(result.stdout)
            assert "permissionDecision" not in output.get("hookSpecificOutput", {})

    def test_normal_python_file_unaffected(self):
        result = run_hook({"tool_name": "Read", "tool_input": {"file_path": "main.py"}, "cwd": "."})
        assert result.stdout.strip() == ""
        assert result.returncode == 0
