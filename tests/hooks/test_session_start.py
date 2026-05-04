"""Tests for SessionStart hook — inject git state and clean up stale artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = str(Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "session_start.py")


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestCleanup:
    def test_removes_stale_markers(self, tmp_path):
        codemonkeys_dir = tmp_path / ".codemonkeys"
        codemonkeys_dir.mkdir()

        markers = [".ruff-warned", ".pyright-warned", ".pytest-warned", ".active-skill"]
        for m in markers:
            (codemonkeys_dir / m).touch()

        gate_dir = codemonkeys_dir / "stop-gate"
        gate_dir.mkdir()
        (gate_dir / "attempt-count").write_text("1")

        run_hook({"cwd": str(tmp_path)})

        for m in markers:
            assert not (codemonkeys_dir / m).exists()
        assert not (gate_dir / "attempt-count").exists()

    def test_truncates_large_failure_log(self, tmp_path):
        log_dir = tmp_path / ".codemonkeys" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "failures.jsonl"
        log_file.write_text("\n".join(f"line {i}" for i in range(600)) + "\n")

        run_hook({"cwd": str(tmp_path)})

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 500

    def test_small_failure_log_untouched(self, tmp_path):
        log_dir = tmp_path / ".codemonkeys" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "failures.jsonl"
        log_file.write_text("line 1\nline 2\n")

        run_hook({"cwd": str(tmp_path)})

        assert log_file.read_text() == "line 1\nline 2\n"

    def test_no_codemonkeys_dir_still_works(self, tmp_path):
        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0


class TestGitInjection:
    def test_outputs_branch_info_in_git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, capture_output=True)

        result = run_hook({"cwd": str(tmp_path)})
        assert "[codemonkeys] branch:" in result.stdout
        assert "uncommitted changes" in result.stdout

    def test_shows_recent_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "first commit"],
            cwd=tmp_path,
            capture_output=True,
            env={**__import__("os").environ, "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
                 "GIT_AUTHOR_EMAIL": "t@t.com", "GIT_COMMITTER_EMAIL": "t@t.com"},
        )

        result = run_hook({"cwd": str(tmp_path)})
        assert "Recent:" in result.stdout
        assert "first commit" in result.stdout

    def test_non_git_dir_exits_silently(self, tmp_path):
        result = run_hook({"cwd": str(tmp_path)})
        assert result.returncode == 0
        assert result.stdout.strip() == ""
