"""Mechanical audit phase — runs subprocess tools and returns structured results."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    HygieneFinding,
    LicenseFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)
from codemonkeys.workflows.events import (
    EventType,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable

# Patterns for secrets scanning
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "Generic API key",
        re.compile(r"api[_\-]?key\s*=\s*['\"][A-Za-z0-9]{20,}['\"]", re.IGNORECASE),
    ),
    (
        "Generic secret",
        re.compile(
            r"(?:secret|password|passwd|token)\s*=\s*['\"][^'\"]{8,}['\"]",
            re.IGNORECASE,
        ),
    ),
    (
        "Private key header",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    ),
]


async def mechanical_audit(ctx: WorkflowContext) -> dict[str, MechanicalAuditResult]:
    """Run enabled mechanical audit tools and return structured results."""
    cwd = Path(ctx.cwd)
    files: list[str] = ctx.phase_results["discover"]["files"]
    enabled: set[str] = ctx.config.audit_tools
    emitter = ctx.emitter

    ruff_findings: list[RuffFinding] = []
    pyright_findings: list[PyrightFinding] = []
    pytest_result: PytestResult | None = None
    pip_audit_findings: list[CveFinding] | None = None
    secrets_findings: list[SecretsFinding] = []
    coverage_map: CoverageMap | None = None
    dead_code_findings: list[DeadCodeFinding] | None = None
    license_compliance_findings: list[LicenseFinding] | None = None
    release_hygiene_findings: list[HygieneFinding] | None = None

    def _emit_start(tool: str) -> float:
        if emitter:
            emitter.emit(
                EventType.MECHANICAL_TOOL_STARTED,
                MechanicalToolStartedPayload(tool=tool, files_count=len(files)),
            )
        return time.time()

    def _emit_done(tool: str, start: float, count: int) -> None:
        if emitter:
            emitter.emit(
                EventType.MECHANICAL_TOOL_COMPLETED,
                MechanicalToolCompletedPayload(
                    tool=tool,
                    findings_count=count,
                    duration_ms=int((time.time() - start) * 1000),
                ),
            )

    if "ruff" in enabled:
        t = _emit_start("ruff")
        ruff_findings = _run_ruff(files, cwd)
        _emit_done("ruff", t, len(ruff_findings))

    if "pyright" in enabled:
        t = _emit_start("pyright")
        pyright_findings = _run_pyright(files, cwd)
        _emit_done("pyright", t, len(pyright_findings))

    if "pytest" in enabled:
        t = _emit_start("pytest")
        pytest_result = _run_pytest(cwd)
        _emit_done("pytest", t, pytest_result.failed + pytest_result.errors)

    if "pip_audit" in enabled:
        t = _emit_start("pip_audit")
        pip_audit_findings = _run_pip_audit(cwd)
        _emit_done("pip_audit", t, len(pip_audit_findings))

    if "secrets" in enabled:
        t = _emit_start("secrets")
        secrets_findings = _scan_secrets(files, cwd)
        _emit_done("secrets", t, len(secrets_findings))

    if "coverage" in enabled:
        t = _emit_start("coverage")
        coverage_map = _compute_coverage(files, cwd)
        _emit_done("coverage", t, len(coverage_map.uncovered))

    if "dead_code" in enabled:
        t = _emit_start("dead_code")
        dead_code_findings = _find_dead_code(files, cwd)
        _emit_done("dead_code", t, len(dead_code_findings))

    if "license_compliance" in enabled:
        t = _emit_start("license_compliance")
        license_compliance_findings = _run_license_compliance(cwd)
        _emit_done("license_compliance", t, len(license_compliance_findings))

    if "release_hygiene" in enabled:
        t = _emit_start("release_hygiene")
        release_hygiene_findings = _run_release_hygiene(files, cwd)
        _emit_done("release_hygiene", t, len(release_hygiene_findings))

    return {
        "mechanical": MechanicalAuditResult(
            ruff=ruff_findings,
            pyright=pyright_findings,
            pytest=pytest_result,
            pip_audit=pip_audit_findings,
            secrets=secrets_findings,
            coverage=coverage_map,
            dead_code=dead_code_findings,
            license_compliance=license_compliance_findings,
            release_hygiene=release_hygiene_findings,
        )
    }


def _run_ruff(files: list[str], cwd: Path) -> list[RuffFinding]:
    """Run ruff check with JSON output and parse findings."""
    if not files:
        return []

    result = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "--output-format=json", *files],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not result.stdout.strip():
        return []

    try:
        raw: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[RuffFinding] = []
    for item in raw:
        findings.append(
            RuffFinding(
                file=item.get("filename", ""),
                line=item.get("location", {}).get("row", 0),
                code=item.get("code", ""),
                message=item.get("message", ""),
            )
        )
    return findings


def _run_pyright(files: list[str], cwd: Path) -> list[PyrightFinding]:
    """Run pyright with JSON output and parse diagnostics."""
    if not files:
        return []

    result = subprocess.run(
        [PYTHON, "-m", "pyright", "--outputjson", *files],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not result.stdout.strip():
        return []

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[PyrightFinding] = []
    diagnostics = raw.get("generalDiagnostics", [])
    for diag in diagnostics:
        severity_raw = diag.get("severity", "information")
        severity = (
            severity_raw
            if severity_raw in ("error", "warning", "information")
            else "information"
        )
        findings.append(
            PyrightFinding(
                file=diag.get("file", ""),
                line=diag.get("range", {}).get("start", {}).get("line", 0),
                severity=severity,
                message=diag.get("message", ""),
            )
        )
    return findings


def _run_pytest(cwd: Path) -> PytestResult:
    """Run pytest and parse pass/fail counts from output."""
    result = subprocess.run(
        [PYTHON, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    output = result.stdout
    passed = 0
    failed = 0
    errors = 0
    failures: list[str] = []

    # Parse summary line like "5 passed", "3 failed, 2 passed", "1 error"
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    error_match = re.search(r"(\d+) error", output)

    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    if error_match:
        errors = int(error_match.group(1))

    # Extract failure identifiers from --tb=line output
    for line in output.splitlines():
        if line.startswith("FAILED "):
            failures.append(line.removeprefix("FAILED ").strip())

    return PytestResult(passed=passed, failed=failed, errors=errors, failures=failures)


def _run_pip_audit(cwd: Path) -> list[CveFinding]:
    """Run pip-audit with JSON output and parse CVE findings."""
    result = subprocess.run(
        [PYTHON, "-m", "pip_audit", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not result.stdout.strip():
        return []

    try:
        raw: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[CveFinding] = []
    for item in raw:
        vulns = item.get("vulns", [])
        for vuln in vulns:
            findings.append(
                CveFinding(
                    package=item.get("name", ""),
                    installed_version=item.get("version", ""),
                    fixed_version=vuln.get("fix_versions", [None])[0]
                    if vuln.get("fix_versions")
                    else None,
                    cve_id=vuln.get("id", ""),
                    severity=vuln.get("severity", "medium").lower(),
                    description=vuln.get("description", ""),
                )
            )
    return findings


def _scan_secrets(files: list[str], cwd: Path) -> list[SecretsFinding]:
    """Regex-based scan for API keys, tokens, passwords, and private keys."""
    findings: list[SecretsFinding] = []

    for file_path in files:
        full_path = cwd / file_path
        if not full_path.exists():
            continue

        try:
            content = full_path.read_text()
        except OSError:
            continue

        for line_num, line in enumerate(content.splitlines(), start=1):
            for pattern_name, pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    # Redact the sensitive portion
                    snippet = line.strip()
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    findings.append(
                        SecretsFinding(
                            file=file_path,
                            line=line_num,
                            pattern=pattern_name,
                            snippet=snippet,
                        )
                    )
                    break  # One finding per line max

    return findings


def _compute_coverage(files: list[str], cwd: Path) -> CoverageMap:
    """Cross-reference source files with test file existence to estimate coverage."""
    covered: list[str] = []
    uncovered: list[str] = []

    test_files = {f for f in files if "test" in Path(f).name.lower()}
    source_files = [f for f in files if f not in test_files]

    for src in source_files:
        src_path = Path(src)
        # Check for corresponding test file patterns
        stem = src_path.stem
        parent = src_path.parent

        test_candidates = [
            parent / f"test_{stem}.py",
            parent / "tests" / f"test_{stem}.py",
            Path("tests") / f"test_{stem}.py",
            Path("tests") / parent / f"test_{stem}.py",
        ]

        has_test = any(
            (cwd / candidate).exists() or str(candidate) in test_files
            for candidate in test_candidates
        )

        if has_test:
            covered.append(src)
        else:
            uncovered.append(src)

    return CoverageMap(covered=covered, uncovered=uncovered)


def _find_dead_code(files: list[str], cwd: Path) -> list[DeadCodeFinding]:
    """Find top-level public functions only referenced at their definition site."""
    findings: list[DeadCodeFinding] = []

    # Collect all top-level public function names and their locations
    definitions: list[tuple[str, str, int]] = []  # (name, file, line)

    for file_path in files:
        full_path = cwd / file_path
        if not full_path.exists():
            continue

        try:
            source = full_path.read_text()
            tree = ast.parse(source, filename=file_path)
        except (SyntaxError, OSError):
            continue

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    definitions.append((node.name, file_path, node.lineno))

    if not definitions:
        return findings

    # Read all file contents for reference checking
    all_contents: dict[str, str] = {}
    for file_path in files:
        full_path = cwd / file_path
        if full_path.exists():
            try:
                all_contents[file_path] = full_path.read_text()
            except OSError:
                pass

    # For each definition, grep across all files
    for name, def_file, def_line in definitions:
        reference_count = 0
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")

        for file_path, content in all_contents.items():
            for line_num, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    # Skip the definition site itself
                    if file_path == def_file and line_num == def_line:
                        continue
                    reference_count += 1
                    break  # Found a reference in this file, that's enough

        if reference_count == 0:
            findings.append(
                DeadCodeFinding(
                    file=def_file,
                    line=def_line,
                    name=name,
                    kind="function",
                )
            )

    return findings


_PERMISSIVE_LICENSES = frozenset(
    {
        "MIT",
        "MIT License",
        "BSD",
        "BSD License",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "ISC License",
        "Apache-2.0",
        "Apache Software License",
        "Unlicense",
        "The Unlicense",
        "PSF",
        "Python Software Foundation License",
        "Python-2.0",
        "0BSD",
        "CC0-1.0",
        "Public Domain",
    }
)

_COPYLEFT_PATTERNS = re.compile(r"GPL|AGPL|LGPL", re.IGNORECASE)

_RESTRICTIVE_LICENSES = frozenset(
    {
        "MPL-2.0",
        "Mozilla Public License 2.0",
        "MPL 2.0",
        "CC-BY-NC",
        "CC-BY-NC-SA",
        "EUPL",
        "EUPL-1.2",
        "CPAL-1.0",
        "OSL-3.0",
    }
)


def _classify_license(license_str: str) -> tuple[str, str] | None:
    """Classify a license string. Returns (category, severity) or None if permissive."""
    normalized = license_str.strip()

    if not normalized or normalized.upper() == "UNKNOWN":
        return ("unknown_license", "medium")

    if any(normalized.upper().startswith(p.upper()) for p in _PERMISSIVE_LICENSES):
        return None

    if _COPYLEFT_PATTERNS.search(normalized):
        return ("copyleft_risk", "high")

    if any(normalized.upper().startswith(r.upper()) for r in _RESTRICTIVE_LICENSES):
        return ("restrictive_license", "low")

    return ("non_standard_license", "low")


def _run_license_compliance(cwd: Path) -> list[LicenseFinding]:
    """Run pip-licenses and classify each package's license."""
    result = subprocess.run(
        [PYTHON, "-m", "piplicenses", "--format=json", "--with-urls", "--with-system"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not result.stdout.strip():
        return []

    try:
        raw: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[LicenseFinding] = []
    for item in raw:
        license_str = item.get("License", "")
        classification = _classify_license(license_str)
        if classification is not None:
            category, severity = classification
            findings.append(
                LicenseFinding(
                    package=item.get("Name", ""),
                    version=item.get("Version", ""),
                    license=license_str,
                    category=category,
                    severity=severity,
                )
            )
    return findings


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
