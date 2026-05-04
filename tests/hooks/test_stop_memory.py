"""Tests for stop_memory hook — project memory after significant changes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_PATH = Path(__file__).resolve().parents[2] / "codemonkeys-plugin" / "hooks" / "stop_memory.py"
HOOK = str(HOOK_PATH)


def run_hook(data: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=10,
    )


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("stop_memory", HOOK_PATH)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestParseDiffStat:
    def test_parses_filenames(self):
        mod = load_module()
        stat = (
            " src/main.py       | 12 ++++++------\n"
            " src/utils.py      |  3 +++\n"
            " tests/test_main.py| 25 +++++++++++++++++++++++++\n"
            " 3 files changed, 28 insertions(+), 6 deletions(-)\n"
        )
        files = mod._parse_diff_stat(stat)
        assert files == ["src/main.py", "src/utils.py", "tests/test_main.py"]

    def test_empty_stat(self):
        mod = load_module()
        assert mod._parse_diff_stat("") == []

    def test_summary_only_line_ignored(self):
        mod = load_module()
        stat = " 3 files changed, 28 insertions(+), 6 deletions(-)\n"
        assert mod._parse_diff_stat(stat) == []


class TestBuildSummary:
    def test_categorizes_files(self, tmp_path):
        mod = load_module()
        files = ["src/main.py", "src/helpers.py", "tests/test_main.py", "README.md"]

        with patch.object(mod, "_get_branch", return_value="feat/cool"):
            summary = mod._build_summary(tmp_path, files)

        assert "feat/cool" in summary
        assert "src/main.py" in summary
        assert "tests/test_main.py" in summary
        assert "README.md" in summary

    def test_truncates_long_src_lists(self, tmp_path):
        mod = load_module()
        files = [f"src/file{i}.py" for i in range(10)]

        with patch.object(mod, "_get_branch", return_value="main"):
            summary = mod._build_summary(tmp_path, files)

        assert "+5 more" in summary


class TestWriteMemory:
    def test_creates_memory_dir_and_file(self, tmp_path):
        mod = load_module()
        mod._write_memory(tmp_path, "## 2026-05-03 — main\nsrc: foo.py")

        index = tmp_path / ".codemonkeys" / "memory" / "MEMORY.md"
        assert index.exists()
        assert "foo.py" in index.read_text()

    def test_appends_to_existing(self, tmp_path):
        mod = load_module()
        memory_dir = tmp_path / ".codemonkeys" / "memory"
        memory_dir.mkdir(parents=True)
        index = memory_dir / "MEMORY.md"
        index.write_text("## existing entry\n")

        mod._write_memory(tmp_path, "## new entry")

        lines = index.read_text().strip().splitlines()
        assert "## existing entry" in lines
        assert "## new entry" in lines

    def test_rotates_at_max_lines(self, tmp_path):
        mod = load_module()
        memory_dir = tmp_path / ".codemonkeys" / "memory"
        memory_dir.mkdir(parents=True)
        index = memory_dir / "MEMORY.md"
        index.write_text("\n".join(f"line {i}" for i in range(50)) + "\n")

        mod._write_memory(tmp_path, "new line")

        lines = index.read_text().strip().splitlines()
        assert len(lines) == 50
        assert lines[-1] == "new line"
        assert lines[0] == "line 1"


class TestThreshold:
    def test_fewer_than_3_files_exits_early(self, tmp_path):
        mod = load_module()
        stat = " src/main.py | 5 +++++\n src/other.py | 3 +++\n 2 files changed\n"

        with patch.object(mod, "_get_session_diff", return_value=stat):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps({"cwd": str(tmp_path)})
                with pytest.raises(SystemExit) as exc_info:
                    mod.main()
                assert exc_info.value.code == 0

        index = tmp_path / ".codemonkeys" / "memory" / "MEMORY.md"
        assert not index.exists()

    def test_3_or_more_files_writes_memory(self, tmp_path):
        mod = load_module()
        stat = (
            " src/a.py | 5 +++++\n"
            " src/b.py | 3 +++\n"
            " src/c.py | 2 ++\n"
            " 3 files changed\n"
        )

        with patch.object(mod, "_get_session_diff", return_value=stat):
            with patch.object(mod, "_get_branch", return_value="feat/test"):
                with patch("sys.stdin") as mock_stdin:
                    mock_stdin.read.return_value = json.dumps({"cwd": str(tmp_path)})
                    with pytest.raises(SystemExit) as exc_info:
                        mod.main()
                    assert exc_info.value.code == 0

        index = tmp_path / ".codemonkeys" / "memory" / "MEMORY.md"
        assert index.exists()
        assert "feat/test" in index.read_text()

    def test_empty_diff_exits_early(self, tmp_path):
        mod = load_module()

        with patch.object(mod, "_get_session_diff", return_value=""):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = json.dumps({"cwd": str(tmp_path)})
                with pytest.raises(SystemExit) as exc_info:
                    mod.main()
                assert exc_info.value.code == 0

        index = tmp_path / ".codemonkeys" / "memory" / "MEMORY.md"
        assert not index.exists()
