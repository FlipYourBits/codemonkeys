"""Tests for Stop hook — quality gate that blocks completion if tests fail."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "stop.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestNoActiveSkill:
    def test_exits_cleanly_without_active_skill(self, tmp_path):
        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_exits_cleanly_with_empty_codemonkeys_dir(self, tmp_path):
        (tmp_path / ".codemonkeys").mkdir()
        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0


class TestQualityGate:
    def test_passes_when_tests_pass(self, tmp_path):
        (tmp_path / ".codemonkeys").mkdir()
        (tmp_path / ".codemonkeys" / ".active-skill").write_text("python-review")
        (tmp_path / "test_ok.py").write_text("def test_pass(): assert True\n")

        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0

    def test_blocks_on_first_failure(self, tmp_path):
        (tmp_path / ".codemonkeys").mkdir()
        (tmp_path / ".codemonkeys" / ".active-skill").write_text("python-feature")
        (tmp_path / "test_fail.py").write_text("def test_bad(): assert False\n")

        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 2
        assert "Attempt 1/2" in result.stderr

    def test_allows_after_two_attempts(self, tmp_path):
        codemonkeys_dir = tmp_path / ".codemonkeys"
        codemonkeys_dir.mkdir()
        (codemonkeys_dir / ".active-skill").write_text("python-feature")
        gate_dir = codemonkeys_dir / "stop-gate"
        gate_dir.mkdir()
        (gate_dir / "attempt-count").write_text("1")

        (tmp_path / "test_fail.py").write_text("def test_bad(): assert False\n")

        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert "still failing after 2 attempts" in result.stdout

    def test_resets_attempts_on_pass(self, tmp_path):
        codemonkeys_dir = tmp_path / ".codemonkeys"
        codemonkeys_dir.mkdir()
        (codemonkeys_dir / ".active-skill").write_text("python-review")
        gate_dir = codemonkeys_dir / "stop-gate"
        gate_dir.mkdir()
        (gate_dir / "attempt-count").write_text("1")

        (tmp_path / "test_ok.py").write_text("def test_pass(): assert True\n")

        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert not (gate_dir / "attempt-count").exists()

    def test_removes_active_skill_after_max_attempts(self, tmp_path):
        codemonkeys_dir = tmp_path / ".codemonkeys"
        codemonkeys_dir.mkdir()
        active_skill = codemonkeys_dir / ".active-skill"
        active_skill.write_text("python-feature")
        gate_dir = codemonkeys_dir / "stop-gate"
        gate_dir.mkdir()
        (gate_dir / "attempt-count").write_text("1")

        (tmp_path / "test_fail.py").write_text("def test_bad(): assert False\n")

        run_hook({"cwd": str(tmp_path)})
        assert not active_skill.exists()
