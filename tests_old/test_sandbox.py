"""Tests for codemonkeys.core.sandbox — runs in subprocesses since Landlock is irrevocable."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

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
            from codemonkeys.core.sandbox import restrict
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
            from codemonkeys.core.sandbox import restrict
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
            from codemonkeys.core.sandbox import restrict
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
            from codemonkeys.core.sandbox import restrict
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
            from codemonkeys.core.sandbox import restrict, is_restricted
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
            from codemonkeys.core.sandbox import restrict
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
            from codemonkeys.core.sandbox import restrict
            try:
                restrict("/nonexistent/path/that/does/not/exist")
                print("FAIL")
            except ValueError:
                print("PASS")
        """)
        assert r.stdout.strip() == "PASS", r.stderr


class TestSandboxInProcess:
    """In-process characterization tests for sandbox module state and pure branches."""

    def test_is_restricted_returns_false_before_any_restrict_call(self) -> None:
        # Import fresh in subprocess to avoid module-level state pollution.
        r = _run_sandboxed("""\
            from codemonkeys.core.sandbox import is_restricted
            print(is_restricted())
        """)
        assert r.stdout.strip() == "False", r.stderr

    def test_restrict_raises_value_error_for_nonexistent_dir(
        self, tmp_path: Path
    ) -> None:
        import codemonkeys.core.sandbox as sandbox_mod

        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="not a directory"):
            sandbox_mod.restrict(nonexistent)

    def test_restrict_unsupported_platform_logs_warning_and_does_not_set_restricted(
        self, tmp_path: Path
    ) -> None:
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = False
            with (
                patch.object(sandbox_mod, "_log") as mock_log,
                patch.object(sys, "platform", "freebsd14"),
            ):
                sandbox_mod.restrict(tmp_path)
                mock_log.warning.assert_called_once()
            assert sandbox_mod._RESTRICTED is False
        finally:
            sandbox_mod._RESTRICTED = original

    def test_restrict_is_idempotent_in_process(self, tmp_path: Path) -> None:
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = True
            # Must return immediately without touching the filesystem for nonexistent path.
            sandbox_mod.restrict(tmp_path / "nonexistent")
        finally:
            sandbox_mod._RESTRICTED = original

    def test_sandbox_env_key_constant(self) -> None:
        from codemonkeys.core.sandbox import _SANDBOX_ENV_KEY

        assert _SANDBOX_ENV_KEY == "CODEMONKEYS_SANDBOXED"

    def test_seatbelt_profile_contains_expected_placeholders(self) -> None:
        from codemonkeys.core.sandbox import _SEATBELT_PROFILE

        assert "{project_dir}" in _SEATBELT_PROFILE
        assert "{claude_dir}" in _SEATBELT_PROFILE
        assert "{claude_data_dir}" in _SEATBELT_PROFILE
        assert "deny default" in _SEATBELT_PROFILE
        assert "file-write*" in _SEATBELT_PROFILE

    def test_restrict_darwin_early_return_when_already_sandboxed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CODEMONKEYS_SANDBOXED is set _restrict_darwin must return without execvp."""
        from codemonkeys.core import sandbox as sandbox_mod

        monkeypatch.setenv("CODEMONKEYS_SANDBOXED", "1")
        sandbox_mod._restrict_darwin(tmp_path)  # must not raise or exec

    def test_restrict_windows_early_return_when_already_sandboxed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CODEMONKEYS_SANDBOXED is set _restrict_windows must return early."""
        from codemonkeys.core import sandbox as sandbox_mod

        monkeypatch.setenv("CODEMONKEYS_SANDBOXED", "1")
        sandbox_mod._restrict_windows(tmp_path)  # must not raise

    def test_is_restricted_returns_false_in_process(self) -> None:
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = False
            assert sandbox_mod.is_restricted() is False
        finally:
            sandbox_mod._RESTRICTED = original

    def test_is_restricted_returns_true_when_flag_set(self) -> None:
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = True
            assert sandbox_mod.is_restricted() is True
        finally:
            sandbox_mod._RESTRICTED = original

    def test_restrict_linux_dispatch_sets_restricted(self, tmp_path: Path) -> None:
        """Patch _restrict_linux to verify restrict() sets _RESTRICTED on linux."""
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = False
            with (
                patch.object(sandbox_mod, "_restrict_linux") as mock_restrict,
                patch.object(sys, "platform", "linux"),
            ):
                sandbox_mod.restrict(tmp_path)
            mock_restrict.assert_called_once_with(tmp_path.resolve())
            assert sandbox_mod._RESTRICTED is True
        finally:
            sandbox_mod._RESTRICTED = original

    def test_restrict_darwin_dispatch_calls_darwin_func(self, tmp_path: Path) -> None:
        """Patch _restrict_darwin to verify restrict() calls it on darwin."""
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = False
            with (
                patch.object(sandbox_mod, "_restrict_darwin") as mock_restrict,
                patch.object(sys, "platform", "darwin"),
            ):
                sandbox_mod.restrict(tmp_path)
            mock_restrict.assert_called_once_with(tmp_path.resolve())
            assert sandbox_mod._RESTRICTED is True
        finally:
            sandbox_mod._RESTRICTED = original

    def test_restrict_win32_dispatch_calls_windows_func(self, tmp_path: Path) -> None:
        """Patch _restrict_windows to verify restrict() calls it on win32."""
        import codemonkeys.core.sandbox as sandbox_mod

        original = sandbox_mod._RESTRICTED
        try:
            sandbox_mod._RESTRICTED = False
            with (
                patch.object(sandbox_mod, "_restrict_windows") as mock_restrict,
                patch.object(sys, "platform", "win32"),
            ):
                sandbox_mod.restrict(tmp_path)
            mock_restrict.assert_called_once_with(tmp_path.resolve())
            assert sandbox_mod._RESTRICTED is True
        finally:
            sandbox_mod._RESTRICTED = original

    def test_restrict_darwin_without_sandbox_env_calls_execvp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_restrict_darwin sets CODEMONKEYS_SANDBOXED and calls os.execvp."""
        from codemonkeys.core import sandbox as sandbox_mod

        monkeypatch.delenv("CODEMONKEYS_SANDBOXED", raising=False)
        with (
            patch.object(os, "execvp") as mock_execvp,
            patch.dict(os.environ, {}, clear=False),
        ):
            sandbox_mod._restrict_darwin(tmp_path)
        mock_execvp.assert_called_once()
        args = mock_execvp.call_args[0]
        assert args[0] == "sandbox-exec"
        assert sys.executable in args[1]

    def test_restrict_darwin_sets_sandbox_env_before_execvp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_restrict_darwin sets CODEMONKEYS_SANDBOXED env var before calling execvp."""
        from codemonkeys.core import sandbox as sandbox_mod

        monkeypatch.delenv("CODEMONKEYS_SANDBOXED", raising=False)
        captured_env: dict[str, str] = {}

        def _capture_execvp(prog, argv):
            captured_env.update(os.environ)

        with patch.object(os, "execvp", side_effect=_capture_execvp):
            sandbox_mod._restrict_darwin(tmp_path)

        assert captured_env.get("CODEMONKEYS_SANDBOXED") == "1"

    def test_restrict_linux_missing_package_logs_warning(self, tmp_path: Path) -> None:
        """When landlock is not installed, _restrict_linux logs a warning and returns."""
        import codemonkeys.core.sandbox as sandbox_mod
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "landlock":
                raise ImportError("No module named 'landlock'")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch.object(sandbox_mod, "_log") as mock_log,
        ):
            sandbox_mod._restrict_linux(tmp_path)
            mock_log.warning.assert_called_once()

    def test_restrict_windows_without_sandbox_env_calls_icacls_and_reexec(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_restrict_windows calls icacls and _reexec_low_integrity when not sandboxed."""
        from codemonkeys.core import sandbox as sandbox_mod

        monkeypatch.delenv("CODEMONKEYS_SANDBOXED", raising=False)
        with (
            patch("subprocess.run") as mock_run,
            patch.object(
                sandbox_mod, "_reexec_low_integrity", create=True
            ) as mock_reexec,
        ):
            sandbox_mod._restrict_windows(tmp_path)
        # icacls is called for directories that exist; tmp_path exists
        assert mock_run.call_count >= 1
        mock_reexec.assert_called_once()
