"""Windows Low Integrity Token sandbox implementation.

This module is Windows-only and must only be imported when sys.platform == "win32".
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wt.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("lpReserved", wt.LPWSTR),
        ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR),
        ("dwX", wt.DWORD),
        ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD),
        ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD),
        ("dwYCountChars", wt.DWORD),
        ("dwFillAttribute", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD),
        ("cbReserved2", wt.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wt.HANDLE),
        ("hStdOutput", wt.HANDLE),
        ("hStdError", wt.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wt.HANDLE),
        ("hThread", wt.HANDLE),
        ("dwProcessId", wt.DWORD),
        ("dwThreadId", wt.DWORD),
    ]


def _reexec_low_integrity() -> None:
    """Re-exec the current process with a Low integrity token (Windows)."""
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
    low_sid = (ctypes.c_byte * 12)(1, 1, 0, 0, 0, 0, 0, 16, 0, 16, 0, 0)

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

    cmdline = " ".join([f'"{sys.executable}"', *[f'"{a}"' for a in sys.argv]])

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    if not advapi32.CreateProcessWithTokenW(
        h_new,
        LOGON_WITH_PROFILE,
        None,
        ctypes.create_unicode_buffer(cmdline),
        0,
        None,
        None,
        ctypes.byref(si),
        ctypes.byref(pi),
    ):
        raise OSError("CreateProcessWithTokenW failed")

    kernel32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)
    exit_code = wt.DWORD()
    kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(exit_code))
    kernel32.CloseHandle(pi.hProcess)
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(h_token)
    kernel32.CloseHandle(h_new)
    sys.exit(exit_code.value)
