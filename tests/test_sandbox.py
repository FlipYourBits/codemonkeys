"""Tests for codemonkeys.sandbox — runs in subprocesses since Landlock is irrevocable."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _run_sandboxed(code: str) -> subprocess.CompletedProcess[str]:
    """Run code in a child process with the project on sys.path."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
class TestLandlockSandbox:
    def test_blocks_writes_outside_project(self) -> None:
        r = _run_sandboxed("""\
            from pathlib import Path
            from codemonkeys.sandbox import restrict
            project = Path("/tmp/sandbox_test_block")
            project.mkdir(exist_ok=True)
            restrict(project)
            try:
                Path("/home/sandbox_escape.txt").write_text("escaped")
                print("FAIL")
            except PermissionError:
                print("PASS")
            project.rmdir()
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_allows_writes_inside_project(self) -> None:
        r = _run_sandboxed("""\
            from pathlib import Path
            from codemonkeys.sandbox import restrict
            project = Path("/tmp/sandbox_test_allow")
            project.mkdir(exist_ok=True)
            restrict(project)
            f = project / "test.txt"
            f.write_text("hello")
            assert f.read_text() == "hello"
            f.unlink()
            project.rmdir()
            print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_allows_writes_to_tmp(self) -> None:
        r = _run_sandboxed("""\
            import tempfile
            from pathlib import Path
            from codemonkeys.sandbox import restrict
            project = Path("/tmp/sandbox_test_tmp")
            project.mkdir(exist_ok=True)
            restrict(project)
            f = Path(tempfile.mktemp(dir="/tmp"))
            f.write_text("temp")
            f.unlink()
            project.rmdir()
            print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_child_process_inherits_restriction(self) -> None:
        r = _run_sandboxed("""\
            import subprocess, sys
            from pathlib import Path
            from codemonkeys.sandbox import restrict
            project = Path("/tmp/sandbox_test_inherit")
            project.mkdir(exist_ok=True)
            restrict(project)
            child = subprocess.run(
                [sys.executable, "-c",
                 "from pathlib import Path\\n"
                 "try:\\n"
                 "    Path('/home/child_escape.txt').write_text('x')\\n"
                 "    print('FAIL')\\n"
                 "except PermissionError:\\n"
                 "    print('PASS')"],
                capture_output=True, text=True,
            )
            print(child.stdout.strip())
            project.rmdir()
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_idempotent(self) -> None:
        r = _run_sandboxed("""\
            from pathlib import Path
            from codemonkeys.sandbox import restrict, is_restricted
            project = Path("/tmp/sandbox_test_idempotent")
            project.mkdir(exist_ok=True)
            restrict(project)
            assert is_restricted()
            restrict(project)  # should be a no-op
            assert is_restricted()
            project.rmdir()
            print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_reads_unrestricted(self) -> None:
        r = _run_sandboxed("""\
            from pathlib import Path
            from codemonkeys.sandbox import restrict
            project = Path("/tmp/sandbox_test_read")
            project.mkdir(exist_ok=True)
            restrict(project)
            # Should be able to read any file on the system
            assert Path("/etc/hostname").exists()
            content = Path("/etc/hostname").read_text()
            assert len(content) > 0
            project.rmdir()
            print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr

    def test_rejects_nonexistent_dir(self) -> None:
        r = _run_sandboxed("""\
            from codemonkeys.sandbox import restrict
            try:
                restrict("/nonexistent/path/that/does/not/exist")
                print("FAIL")
            except ValueError:
                print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr
