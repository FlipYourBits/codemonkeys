"""OS-level filesystem sandbox — restricts writes to the project directory.

Call ``restrict()`` once at startup. From that point on, the current process
and all child processes (including SDK-spawned agents) can only write inside
the allowed directory. Reads are unrestricted.

Backends:
    - Linux: Landlock LSM (kernel 5.13+, ``landlock`` package)
    - macOS: sandbox-exec / Seatbelt (re-execs the process inside a profile)
    - Windows: Low Integrity Token (re-execs with a restricted process token)

The restriction is irrevocable for the lifetime of the process.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

# Module-level state is required here: the OS sandbox call (Landlock /
# Seatbelt / Low Integrity Token) is irrevocable for the process lifetime,
# so we guard against double-application across all callers in the process.
_RESTRICTED = False


def restrict(project_dir: str | Path) -> None:
    """Restrict filesystem writes to *project_dir* for this process and all children.

    Safe to call multiple times — subsequent calls are no-ops.
    Raises ``RuntimeError`` on unsupported platforms (unless the platform
    has a re-exec backend like macOS, in which case this function does not return).
    """
    global _RESTRICTED  # noqa: PLW0603
    if _RESTRICTED:
        return

    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise ValueError(f"project_dir is not a directory: {project}")

    platform = sys.platform
    if platform == "linux":
        _restrict_linux(project)
    elif platform == "darwin":
        _restrict_darwin(project)
    elif platform == "win32":
        _restrict_windows(project)
    else:
        _log.warning(
            "Filesystem sandboxing not available on %s — "
            "relying on prompt-level path restrictions only",
            platform,
        )
        return

    _RESTRICTED = True
    _log.info("Filesystem writes restricted to %s", project)


def is_restricted() -> bool:
    """Return whether the sandbox has been applied."""
    return _RESTRICTED


# ---------------------------------------------------------------------------
# Linux — Landlock LSM
# ---------------------------------------------------------------------------


def _restrict_linux(project: Path) -> None:
    try:
        from landlock import FSAccess, Ruleset
    except ImportError:
        _log.warning(
            "landlock package not installed — install it with: pip install landlock"
        )
        return

    write_flags = (
        FSAccess.WRITE_FILE
        | FSAccess.MAKE_REG
        | FSAccess.MAKE_DIR
        | FSAccess.REMOVE_FILE
        | FSAccess.REMOVE_DIR
        | FSAccess.TRUNCATE
        | FSAccess.MAKE_SYM
        | FSAccess.MAKE_SOCK
        | FSAccess.MAKE_FIFO
        | FSAccess.MAKE_CHAR
        | FSAccess.MAKE_BLOCK
    )

    rs = Ruleset()

    rs.allow(str(project))

    rs.allow("/", rules=FSAccess.READ_FILE | FSAccess.READ_DIR | FSAccess.EXECUTE)

    rs.allow("/tmp", rules=write_flags)
    rs.allow("/dev", rules=FSAccess.WRITE_FILE)

    # Claude CLI needs write access to its own state directories.
    home = Path.home()
    for claude_dir in (home / ".claude", home / ".local" / "share" / "claude"):
        if claude_dir.is_dir():
            rs.allow(str(claude_dir), rules=write_flags)

    rs.apply()


# ---------------------------------------------------------------------------
# macOS — sandbox-exec (Seatbelt)
# ---------------------------------------------------------------------------

_SEATBELT_PROFILE = """\
(version 1)
(deny default)

;; Allow everything except filesystem writes outside the project dir.
(allow process*)
(allow sysctl*)
(allow mach*)
(allow ipc*)
(allow signal)
(allow network*)
(allow system*)

;; Read access everywhere.
(allow file-read*)

;; Write access only to the project directory, /tmp, and Claude CLI state.
(allow file-write* (subpath "{project_dir}"))
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "/private/tmp"))
(allow file-write* (subpath "/dev"))
(allow file-write* (subpath "{claude_dir}"))
(allow file-write* (subpath "{claude_data_dir}"))
"""

_SANDBOX_ENV_KEY = "CODEMONKEYS_SANDBOXED"


def _restrict_darwin(project: Path) -> None:
    if os.environ.get(_SANDBOX_ENV_KEY):
        # Already inside the sandbox — the re-exec worked.
        return

    home = Path.home()
    profile = _SEATBELT_PROFILE.format(
        project_dir=str(project),
        claude_dir=str(home / ".claude"),
        claude_data_dir=str(home / ".local" / "share" / "claude"),
    )

    os.environ[_SANDBOX_ENV_KEY] = "1"
    os.execvp(
        "sandbox-exec",
        ["sandbox-exec", "-p", profile, "--", sys.executable, *sys.argv],
    )


# ---------------------------------------------------------------------------
# Windows — Low Integrity Token
# ---------------------------------------------------------------------------
#
# Windows processes run at Medium integrity by default. Medium-integrity
# processes cannot write to objects labeled Low, but Low-integrity processes
# cannot write to Medium-labeled objects (which is everything by default).
#
# Strategy: mark the allowed directories as Low-integrity-writable via
# icacls, then re-exec the current process with a Low integrity token.
# Child processes inherit the Low token and cannot write anywhere that
# hasn't been explicitly labeled.


def _restrict_windows(project: Path) -> None:
    if os.environ.get(_SANDBOX_ENV_KEY):
        return

    import subprocess

    home = Path.home()
    writable_dirs = [
        project,
        Path(os.environ.get("TEMP", home / "AppData" / "Local" / "Temp")),
        home / ".claude",
    ]
    claude_data = home / "AppData" / "Local" / "claude"
    if claude_data.is_dir():
        writable_dirs.append(claude_data)

    for d in writable_dirs:
        if d.is_dir():
            subprocess.run(
                ["icacls", str(d), "/setintegritylevel", "(OI)(CI)low"],
                check=True,
                capture_output=True,
            )

    os.environ[_SANDBOX_ENV_KEY] = "1"
    _reexec_low_integrity()  # type: ignore[name-defined]


if sys.platform == "win32":
    # Import Windows-specific implementation; only safe to import on Win32 because
    # it references ctypes.wintypes which does not exist on other platforms.
    from codemonkeys.core._sandbox_win32 import _reexec_low_integrity  # noqa: F401
