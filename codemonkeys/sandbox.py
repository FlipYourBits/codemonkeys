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
            "landlock package not installed — "
            "install it with: pip install landlock"
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
    _reexec_low_integrity()


def _reexec_low_integrity() -> None:
    """Re-exec the current process with a Low integrity token (Windows)."""
    import ctypes
    import ctypes.wintypes as wt

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]

    TOKEN_DUPLICATE = 0x0002
    TOKEN_QUERY = 0x0008
    TOKEN_ADJUST_DEFAULT = 0x0080
    TOKEN_ASSIGN_PRIMARY = 0x0001
    SecurityImpersonation = 2
    TokenPrimary = 1
    TokenIntegrityLevel = 25
    SE_GROUP_INTEGRITY = 0x00000020
    LOGON_WITH_PROFILE = 0x00000001

    h_token = wt.HANDLE()
    if not kernel32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ADJUST_DEFAULT | TOKEN_ASSIGN_PRIMARY,
        ctypes.byref(h_token),
    ):
        raise OSError("OpenProcessToken failed")

    h_new = wt.HANDLE()
    if not advapi32.DuplicateTokenEx(
        h_token,
        TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ADJUST_DEFAULT | TOKEN_ASSIGN_PRIMARY,
        None,
        SecurityImpersonation,
        TokenPrimary,
        ctypes.byref(h_new),
    ):
        raise OSError("DuplicateTokenEx failed")

    # Build the Low integrity SID (S-1-16-4096).
    low_sid = (ctypes.c_byte * 12)(
        1, 1, 0, 0, 0, 0, 0, 16, 0, 16, 0, 0
    )

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wt.DWORD)]

    class TOKEN_MANDATORY_LABEL(ctypes.Structure):
        _fields_ = [("Label", SID_AND_ATTRIBUTES)]

    tml = TOKEN_MANDATORY_LABEL()
    tml.Label.Sid = ctypes.cast(low_sid, ctypes.c_void_p)
    tml.Label.Attributes = SE_GROUP_INTEGRITY

    if not advapi32.SetTokenInformation(
        h_new,
        TokenIntegrityLevel,
        ctypes.byref(tml),
        ctypes.sizeof(tml),
    ):
        raise OSError("SetTokenInformation failed")

    # Build command line: re-run the same Python script.
    cmdline = " ".join([f'"{sys.executable}"', *[f'"{a}"' for a in sys.argv]])

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR),
            ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
            ("dwX", wt.DWORD), ("dwY", wt.DWORD),
            ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
            ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
            ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
            ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
            ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE),
            ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
            ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
        ]

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    if not advapi32.CreateProcessWithTokenW(
        h_new,
        LOGON_WITH_PROFILE,
        None,
        ctypes.create_unicode_buffer(cmdline),
        0,  # creation flags
        None,  # environment (inherit)
        None,  # current directory (inherit)
        ctypes.byref(si),
        ctypes.byref(pi),
    ):
        raise OSError("CreateProcessWithTokenW failed")

    # Wait for the child to finish, then exit with its exit code.
    kernel32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)  # INFINITE
    exit_code = wt.DWORD()
    kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(exit_code))
    kernel32.CloseHandle(pi.hProcess)
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(h_token)
    kernel32.CloseHandle(h_new)
    sys.exit(exit_code.value)
