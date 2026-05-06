"""Release hygiene scanner for the mechanical audit."""

from __future__ import annotations

import re
from pathlib import Path

from codemonkeys.artifacts.schemas.mechanical import HygieneFinding


# Patterns for release hygiene scanning
_DEBUG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("breakpoint() call", re.compile(r"\bbreakpoint\s*\(")),
    ("pdb import", re.compile(r"^\s*import\s+(?:pdb|ipdb|pudb)\b")),
    ("debugpy import", re.compile(r"^\s*import\s+debugpy\b")),
    ("debugpy.listen call", re.compile(r"\bdebugpy\.listen\b")),
]

_PRINT_PATTERN = re.compile(r"\bprint\s*\(")

_TODO_BARE = re.compile(r"#\s*(?:TODO|FIXME|HACK|XXX)\b(?!\s*\(#?\d+\))", re.IGNORECASE)

_SKIP_NO_REASON = re.compile(r"@pytest\.mark\.skip\s*(?:\(\s*\))?$")

_LOCALHOST_PATTERN = re.compile(
    r"""(?:localhost|127\.0\.0\.1|0\.0\.0\.0)""", re.IGNORECASE
)

_DEBUG_TRUE_PATTERN = re.compile(r"\bdebug\s*=\s*True\b", re.IGNORECASE)

_SKIP_FILE_PATTERNS = re.compile(
    r"(?:^|/)(?:test_|conftest\.py|.*config.*|.*settings.*|.*\.env.*|.*example.*)",
    re.IGNORECASE,
)

_SKIP_PRINT_PATTERNS = re.compile(
    r"(?:^|/)(?:test_|conftest\.py|cli/|__main__\.py)", re.IGNORECASE
)


def _run_release_hygiene(files: list[str], cwd: Path) -> list[HygieneFinding]:
    """Scan files for debug artifacts, unresolved markers, and hardcoded dev values."""
    findings: list[HygieneFinding] = []

    for file_path in files:
        full_path = cwd / file_path
        if not full_path.exists():
            continue

        try:
            content = full_path.read_text()
        except OSError:
            continue

        is_skip_file = bool(_SKIP_FILE_PATTERNS.search(file_path))
        is_skip_print = bool(_SKIP_PRINT_PATTERNS.search(file_path))

        for line_num, line in enumerate(content.splitlines(), start=1):
            # Debug artifacts
            for detail, pattern in _DEBUG_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        HygieneFinding(
                            file=file_path,
                            line=line_num,
                            category="debug_artifact",
                            detail=detail,
                            severity="medium",
                        )
                    )
                    break

            # print() in non-test, non-CLI files
            if not is_skip_print and _PRINT_PATTERN.search(line):
                if not line.strip().startswith("#"):
                    findings.append(
                        HygieneFinding(
                            file=file_path,
                            line=line_num,
                            category="debug_artifact",
                            detail="print() call",
                            severity="medium",
                        )
                    )

            # Bare TODO/FIXME/HACK/XXX
            if _TODO_BARE.search(line):
                findings.append(
                    HygieneFinding(
                        file=file_path,
                        line=line_num,
                        category="unresolved_marker",
                        detail=line.strip(),
                        severity="low",
                    )
                )

            # @pytest.mark.skip without reason
            if _SKIP_NO_REASON.search(line.strip()):
                findings.append(
                    HygieneFinding(
                        file=file_path,
                        line=line_num,
                        category="unresolved_marker",
                        detail="@pytest.mark.skip without reason",
                        severity="low",
                    )
                )

            # Hardcoded dev values — skip test and config files
            if not is_skip_file:
                if _LOCALHOST_PATTERN.search(line) and not line.strip().startswith("#"):
                    findings.append(
                        HygieneFinding(
                            file=file_path,
                            line=line_num,
                            category="hardcoded_dev_value",
                            detail="Hardcoded localhost/loopback address",
                            severity="high",
                        )
                    )

                if _DEBUG_TRUE_PATTERN.search(line) and not line.strip().startswith(
                    "#"
                ):
                    findings.append(
                        HygieneFinding(
                            file=file_path,
                            line=line_num,
                            category="hardcoded_dev_value",
                            detail="debug=True",
                            severity="high",
                        )
                    )

    # Dependency pinning: check for lockfile
    lockfile_names = ["uv.lock", "requirements.lock", "poetry.lock"]
    has_lockfile = any((cwd / name).exists() for name in lockfile_names)
    if not has_lockfile:
        findings.append(
            HygieneFinding(
                file="",
                line=None,
                category="dependency_pinning",
                detail="No lockfile found (uv.lock, requirements.lock, or poetry.lock)",
                severity="medium",
            )
        )

    return findings
