# Review Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 new review capabilities — resilience review prompt, test quality prompt, license compliance tool, release hygiene tool — to the existing review pipeline with zero token cost increase for quick review modes.

**Architecture:** Two new prompt templates (`RESILIENCE_REVIEW`, `TEST_QUALITY`) injected conditionally into the existing `make_python_file_reviewer` agent factory. Two new mechanical tools (`license_compliance`, `release_hygiene`) added as subprocess/regex tools in `mechanical.py` with Pydantic schemas. All wired into workflow compositions via existing patterns.

**Tech Stack:** Python 3.10+, Pydantic v2, pytest, pytest-asyncio, pip-licenses

---

### Task 1: Add `LicenseFinding` and `HygieneFinding` schemas

**Files:**
- Modify: `codemonkeys/artifacts/schemas/mechanical.py:79-97`
- Test: `tests/test_mechanical_schemas.py`

- [ ] **Step 1: Write failing tests for `LicenseFinding`**

```python
# Add to tests/test_mechanical_schemas.py

class TestLicenseFinding:
    def test_roundtrip_json(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import LicenseFinding

        finding = LicenseFinding(
            package="some-gpl-lib",
            version="2.0.0",
            license="GPL-3.0",
            category="copyleft_risk",
            severity="high",
        )
        data = json.loads(finding.model_dump_json())
        restored = LicenseFinding.model_validate(data)
        assert restored == finding

    def test_invalid_category(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import LicenseFinding

        with pytest.raises(ValidationError):
            LicenseFinding(
                package="foo",
                version="1.0",
                license="MIT",
                category="bad_category",  # type: ignore[arg-type]
                severity="low",
            )

    def test_json_schema_has_descriptions(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import LicenseFinding

        schema = LicenseFinding.model_json_schema()
        for field_name in ("package", "version", "license", "category", "severity"):
            assert "description" in schema["properties"][field_name]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mechanical_schemas.py::TestLicenseFinding -v`
Expected: FAIL with `ImportError: cannot import name 'LicenseFinding'`

- [ ] **Step 3: Implement `LicenseFinding` schema**

Add to `codemonkeys/artifacts/schemas/mechanical.py` before `MechanicalAuditResult`:

```python
class LicenseFinding(BaseModel):
    package: str = Field(description="Package name")
    version: str = Field(description="Installed version")
    license: str = Field(description="License string from metadata")
    category: Literal[
        "copyleft_risk",
        "unknown_license",
        "restrictive_license",
        "non_standard_license",
    ] = Field(description="Risk category")
    severity: Literal["high", "medium", "low"] = Field(description="Risk level")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mechanical_schemas.py::TestLicenseFinding -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write failing tests for `HygieneFinding`**

```python
# Add to tests/test_mechanical_schemas.py

class TestHygieneFinding:
    def test_roundtrip_json(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import HygieneFinding

        finding = HygieneFinding(
            file="src/app.py",
            line=42,
            category="debug_artifact",
            detail="breakpoint() call",
            severity="medium",
        )
        data = json.loads(finding.model_dump_json())
        restored = HygieneFinding.model_validate(data)
        assert restored == finding

    def test_line_nullable(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import HygieneFinding

        finding = HygieneFinding(
            file="pyproject.toml",
            line=None,
            category="dependency_pinning",
            detail="No lockfile found",
            severity="medium",
        )
        assert finding.line is None

    def test_invalid_category(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import HygieneFinding

        with pytest.raises(ValidationError):
            HygieneFinding(
                file="a.py",
                line=1,
                category="invalid",  # type: ignore[arg-type]
                detail="test",
                severity="low",
            )

    def test_json_schema_has_descriptions(self) -> None:
        from codemonkeys.artifacts.schemas.mechanical import HygieneFinding

        schema = HygieneFinding.model_json_schema()
        for field_name in ("file", "line", "category", "detail", "severity"):
            assert "description" in schema["properties"][field_name]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_mechanical_schemas.py::TestHygieneFinding -v`
Expected: FAIL with `ImportError: cannot import name 'HygieneFinding'`

- [ ] **Step 7: Implement `HygieneFinding` schema**

Add to `codemonkeys/artifacts/schemas/mechanical.py` before `MechanicalAuditResult`:

```python
class HygieneFinding(BaseModel):
    file: str = Field(description="File path")
    line: int | None = Field(description="Line number, if applicable")
    category: Literal[
        "debug_artifact",
        "unresolved_marker",
        "hardcoded_dev_value",
        "dependency_pinning",
    ] = Field(description="Issue category")
    detail: str = Field(description="What was found")
    severity: Literal["high", "medium", "low"] = Field(description="Risk level")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_mechanical_schemas.py::TestHygieneFinding -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Add both schemas to `MechanicalAuditResult` and update test**

Add two new fields to `MechanicalAuditResult` in `codemonkeys/artifacts/schemas/mechanical.py`:

```python
class MechanicalAuditResult(BaseModel):
    ruff: list[RuffFinding] = Field(description="Lint violations found by ruff")
    pyright: list[PyrightFinding] = Field(description="Type errors found by pyright")
    pytest: PytestResult | None = Field(
        description="Test suite results, or null if tests were not run"
    )
    pip_audit: list[CveFinding] | None = Field(
        description="Known vulnerabilities in dependencies, or null if audit was not run"
    )
    secrets: list[SecretsFinding] = Field(
        description="Secrets or credentials detected in source files"
    )
    coverage: CoverageMap | None = Field(
        description="Test coverage mapping, or null if coverage was not collected"
    )
    dead_code: list[DeadCodeFinding] | None = Field(
        description="Unused code detected by static analysis, or null if not run"
    )
    license_compliance: list[LicenseFinding] | None = Field(
        default=None,
        description="License issues in dependencies, or null if not run",
    )
    release_hygiene: list[HygieneFinding] | None = Field(
        default=None,
        description="Development artifacts and release hygiene issues, or null if not run",
    )
```

Update `TestMechanicalAuditResult` in `tests/test_mechanical_schemas.py`:

In `test_roundtrip_json`, add to the `MechanicalAuditResult(...)` constructor:
```python
            license_compliance=[
                LicenseFinding(
                    package="some-gpl-lib",
                    version="2.0.0",
                    license="GPL-3.0",
                    category="copyleft_risk",
                    severity="high",
                ),
            ],
            release_hygiene=[
                HygieneFinding(
                    file="src/debug.py",
                    line=10,
                    category="debug_artifact",
                    detail="breakpoint() call",
                    severity="medium",
                ),
            ],
```

In `test_nullable_fields`, add:
```python
            license_compliance=None,
            release_hygiene=None,
```
And add assertions:
```python
        assert result.license_compliance is None
        assert result.release_hygiene is None
```

In `test_json_schema_has_descriptions`, add `"license_compliance"` and `"release_hygiene"` to the field names tuple.

Update the imports at the top of `tests/test_mechanical_schemas.py` to include `LicenseFinding` and `HygieneFinding`.

- [ ] **Step 10: Run full mechanical schema tests**

Run: `uv run pytest tests/test_mechanical_schemas.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add codemonkeys/artifacts/schemas/mechanical.py tests/test_mechanical_schemas.py
git commit -m "feat: add LicenseFinding and HygieneFinding schemas to mechanical audit"
```

---

### Task 2: Implement `_run_license_compliance` mechanical tool

**Files:**
- Modify: `codemonkeys/workflows/phase_library/mechanical.py`
- Test: `tests/test_mechanical_phase.py`

- [ ] **Step 1: Write failing test for license compliance runner**

Add to `tests/test_mechanical_phase.py`:

```python
class TestLicenseCompliance:
    def test_classifies_gpl_as_copyleft(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import (
            _run_license_compliance,
        )

        pip_licenses_json = json.dumps([
            {"Name": "some-lib", "Version": "1.0", "License": "GPL-3.0"},
            {"Name": "ok-lib", "Version": "2.0", "License": "MIT"},
        ])

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].package == "some-lib"
        assert findings[0].category == "copyleft_risk"
        assert findings[0].severity == "high"

    def test_classifies_unknown_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import (
            _run_license_compliance,
        )

        pip_licenses_json = json.dumps([
            {"Name": "mystery-lib", "Version": "0.1", "License": "UNKNOWN"},
        ])

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "unknown_license"
        assert findings[0].severity == "medium"

    def test_permissive_licenses_pass(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import (
            _run_license_compliance,
        )

        pip_licenses_json = json.dumps([
            {"Name": "lib-a", "Version": "1.0", "License": "MIT"},
            {"Name": "lib-b", "Version": "2.0", "License": "BSD-3-Clause"},
            {"Name": "lib-c", "Version": "3.0", "License": "Apache-2.0"},
            {"Name": "lib-d", "Version": "1.0", "License": "ISC"},
        ])

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert findings == []

    def test_classifies_restrictive_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import (
            _run_license_compliance,
        )

        pip_licenses_json = json.dumps([
            {"Name": "mpl-lib", "Version": "1.0", "License": "MPL-2.0"},
        ])

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "restrictive_license"
        assert findings[0].severity == "low"

    def test_classifies_non_standard_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import (
            _run_license_compliance,
        )

        pip_licenses_json = json.dumps([
            {"Name": "weird-lib", "Version": "1.0", "License": "Custom License v3"},
        ])

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "non_standard_license"
        assert findings[0].severity == "low"
```

Add `import json` to the test file imports if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mechanical_phase.py::TestLicenseCompliance -v`
Expected: FAIL with `ImportError: cannot import name '_run_license_compliance'`

- [ ] **Step 3: Implement `_run_license_compliance`**

Add to `codemonkeys/workflows/phase_library/mechanical.py` after `_find_dead_code`:

```python
_PERMISSIVE_LICENSES = frozenset({
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
})

_COPYLEFT_PATTERNS = re.compile(r"GPL|AGPL|LGPL", re.IGNORECASE)

_RESTRICTIVE_LICENSES = frozenset({
    "MPL-2.0",
    "Mozilla Public License 2.0",
    "MPL 2.0",
    "CC-BY-NC",
    "CC-BY-NC-SA",
    "EUPL",
    "EUPL-1.2",
    "CPAL-1.0",
    "OSL-3.0",
})


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
```

Add `LicenseFinding` to the imports from `codemonkeys.artifacts.schemas.mechanical` at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mechanical_phase.py::TestLicenseCompliance -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/mechanical.py tests/test_mechanical_phase.py
git commit -m "feat: add license compliance mechanical tool"
```

---

### Task 3: Implement `_run_release_hygiene` mechanical tool

**Files:**
- Modify: `codemonkeys/workflows/phase_library/mechanical.py`
- Test: `tests/test_mechanical_phase.py`

- [ ] **Step 1: Write failing tests for release hygiene**

Add to `tests/test_mechanical_phase.py`:

```python
class TestReleaseHygiene:
    def test_detects_breakpoint(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "app.py"
        target.write_text("x = 1\nbreakpoint()\ny = 2\n")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        assert len(findings) == 1
        assert findings[0].category == "debug_artifact"
        assert findings[0].line == 2

    def test_detects_import_pdb(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "app.py"
        target.write_text("import pdb\npdb.set_trace()\n")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        debug_findings = [f for f in findings if f.category == "debug_artifact"]
        assert len(debug_findings) >= 1

    def test_skips_print_in_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "test_app.py"
        target.write_text('print("debug output")\n')

        findings = _run_release_hygiene(["test_app.py"], tmp_path)
        print_findings = [
            f for f in findings
            if f.category == "debug_artifact" and "print" in f.detail.lower()
        ]
        assert print_findings == []

    def test_detects_bare_todo(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "app.py"
        target.write_text("# TODO fix this later\nx = 1\n")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        marker_findings = [f for f in findings if f.category == "unresolved_marker"]
        assert len(marker_findings) == 1

    def test_allows_todo_with_issue_ref(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "app.py"
        target.write_text("# TODO(#123) fix this later\nx = 1\n")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        marker_findings = [f for f in findings if f.category == "unresolved_marker"]
        assert marker_findings == []

    def test_detects_localhost(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "client.py"
        target.write_text('URL = "http://localhost:8080/api"\n')

        findings = _run_release_hygiene(["client.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert len(dev_findings) == 1
        assert dev_findings[0].severity == "high"

    def test_skips_localhost_in_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "test_client.py"
        target.write_text('URL = "http://localhost:8080/api"\n')

        findings = _run_release_hygiene(["test_client.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert dev_findings == []

    def test_skips_localhost_in_config_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "config.py"
        target.write_text('DEFAULT_HOST = "localhost"\n')

        findings = _run_release_hygiene(["config.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert dev_findings == []

    def test_detects_missing_lockfile(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')

        findings = _run_release_hygiene([], tmp_path)
        pin_findings = [f for f in findings if f.category == "dependency_pinning"]
        lockfile_findings = [f for f in pin_findings if "lockfile" in f.detail.lower()]
        assert len(lockfile_findings) == 1

    def test_no_lockfile_finding_when_present(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        (tmp_path / "uv.lock").write_text("# lock\n")

        findings = _run_release_hygiene([], tmp_path)
        lockfile_findings = [
            f for f in findings
            if f.category == "dependency_pinning" and "lockfile" in f.detail.lower()
        ]
        assert lockfile_findings == []

    def test_clean_file_no_findings(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _run_release_hygiene

        target = tmp_path / "clean.py"
        target.write_text("def hello() -> str:\n    return 'world'\n")
        (tmp_path / "uv.lock").write_text("# lock\n")

        findings = _run_release_hygiene(["clean.py"], tmp_path)
        assert findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mechanical_phase.py::TestReleaseHygiene -v`
Expected: FAIL with `ImportError: cannot import name '_run_release_hygiene'`

- [ ] **Step 3: Implement `_run_release_hygiene`**

Add to `codemonkeys/workflows/phase_library/mechanical.py` after `_run_license_compliance`:

```python
_DEBUG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("breakpoint() call", re.compile(r"\bbreakpoint\s*\(")),
    ("pdb import", re.compile(r"^\s*import\s+(?:pdb|ipdb|pudb)\b")),
    ("debugpy import", re.compile(r"^\s*import\s+debugpy\b")),
    ("debugpy.listen call", re.compile(r"\bdebugpy\.listen\b")),
]

_PRINT_PATTERN = re.compile(r"\bprint\s*\(")

_TODO_BARE = re.compile(
    r"#\s*(?:TODO|FIXME|HACK|XXX)\b(?!\s*\(#?\d+\))", re.IGNORECASE
)

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

        is_test = bool(re.search(r"(?:^|/)test_", file_path))
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

                if _DEBUG_TRUE_PATTERN.search(line) and not line.strip().startswith("#"):
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
```

Add `HygieneFinding` to the imports from `codemonkeys.artifacts.schemas.mechanical` at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mechanical_phase.py::TestReleaseHygiene -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/workflows/phase_library/mechanical.py tests/test_mechanical_phase.py
git commit -m "feat: add release hygiene mechanical tool"
```

---

### Task 4: Wire mechanical tools into audit dispatch and compositions

**Files:**
- Modify: `codemonkeys/workflows/phase_library/mechanical.py:54-133`
- Modify: `codemonkeys/workflows/compositions.py:33-44`
- Test: `tests/test_mechanical_phase.py`
- Test: `tests/test_compositions.py`

- [ ] **Step 1: Write failing test for license_compliance in mechanical audit dispatch**

Add to `tests/test_mechanical_phase.py` inside `TestMechanicalAudit`:

```python
    @pytest.mark.asyncio
    async def test_runs_license_compliance(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        pip_licenses_json = '[{"Name": "gpl-lib", "Version": "1.0", "License": "GPL-3.0"}]'

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"license_compliance"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].license_compliance is not None
        assert len(result["mechanical"].license_compliance) == 1
```

Add `import json` to the imports at the top if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mechanical_phase.py::TestMechanicalAudit::test_runs_license_compliance -v`
Expected: FAIL — `license_compliance` not dispatched in `mechanical_audit`

- [ ] **Step 3: Wire `license_compliance` into `mechanical_audit()` dispatch**

In `codemonkeys/workflows/phase_library/mechanical.py`, in the `mechanical_audit` function:

After the variable initializations (line ~67), add:
```python
    license_compliance_findings: list[LicenseFinding] | None = None
```

After the `dead_code` dispatch block (around line 121), add:
```python
    if "license_compliance" in enabled:
        t = _emit_start("license_compliance")
        license_compliance_findings = _run_license_compliance(cwd)
        _emit_done("license_compliance", t, len(license_compliance_findings))
```

In the return statement, add:
```python
            license_compliance=license_compliance_findings,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mechanical_phase.py::TestMechanicalAudit::test_runs_license_compliance -v`
Expected: PASS

- [ ] **Step 5: Write failing test for release_hygiene in mechanical audit dispatch**

Add to `tests/test_mechanical_phase.py` inside `TestMechanicalAudit`:

```python
    @pytest.mark.asyncio
    async def test_runs_release_hygiene(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        target = tmp_path / "app.py"
        target.write_text("breakpoint()\n")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["app.py"]),
            phase_results={"discover": {"files": ["app.py"]}},
        )
        ctx.config.audit_tools = {"release_hygiene"}
        result = await mechanical_audit(ctx)

        assert result["mechanical"].release_hygiene is not None
        assert len(result["mechanical"].release_hygiene) >= 1
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_mechanical_phase.py::TestMechanicalAudit::test_runs_release_hygiene -v`
Expected: FAIL — `release_hygiene` not dispatched

- [ ] **Step 7: Wire `release_hygiene` into `mechanical_audit()` dispatch**

In `codemonkeys/workflows/phase_library/mechanical.py`, in the `mechanical_audit` function:

After the variable initializations, add:
```python
    release_hygiene_findings: list[HygieneFinding] | None = None
```

After the `license_compliance` dispatch block, add:
```python
    if "release_hygiene" in enabled:
        t = _emit_start("release_hygiene")
        release_hygiene_findings = _run_release_hygiene(files, cwd)
        _emit_done("release_hygiene", t, len(release_hygiene_findings))
```

In the return statement, add:
```python
            release_hygiene=release_hygiene_findings,
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_mechanical_phase.py::TestMechanicalAudit::test_runs_release_hygiene -v`
Expected: PASS

- [ ] **Step 9: Write failing test for updated `ALL_TOOLS` in compositions**

Add to `tests/test_compositions.py` inside `TestReviewConfig`:

```python
    def test_full_repo_includes_new_tools(self) -> None:
        config = ReviewConfig(mode="full_repo")
        assert "license_compliance" in config.audit_tools
        assert "release_hygiene" in config.audit_tools

    def test_diff_includes_new_tools(self) -> None:
        config = ReviewConfig(mode="diff")
        assert "license_compliance" in config.audit_tools
        assert "release_hygiene" in config.audit_tools
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `uv run pytest tests/test_compositions.py::TestReviewConfig::test_full_repo_includes_new_tools tests/test_compositions.py::TestReviewConfig::test_diff_includes_new_tools -v`
Expected: FAIL — new tools not in `ALL_TOOLS` or `SCOPED_TOOLS`

- [ ] **Step 11: Update `ALL_TOOLS` and `SCOPED_TOOLS` in compositions.py**

In `codemonkeys/workflows/compositions.py`, update:

```python
ALL_TOOLS = frozenset(
    {"ruff", "pyright", "pytest", "pip_audit", "secrets", "coverage", "dead_code",
     "license_compliance", "release_hygiene"}
)
SCOPED_TOOLS = frozenset(
    {"ruff", "pyright", "pytest", "secrets", "coverage",
     "license_compliance", "release_hygiene"}
)
```

- [ ] **Step 12: Update existing composition tests that assert exact tool sets**

In `tests/test_compositions.py`, update `test_full_repo_config`:
```python
    def test_full_repo_config(self) -> None:
        config = ReviewConfig(mode="full_repo")
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "pip_audit",
            "secrets",
            "coverage",
            "dead_code",
            "license_compliance",
            "release_hygiene",
        }
```

Update `test_diff_config`:
```python
    def test_diff_config(self) -> None:
        config = ReviewConfig(mode="diff")
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
            "license_compliance",
            "release_hygiene",
        }
        assert "pip_audit" not in config.audit_tools
```

Update `test_files_config`:
```python
    def test_files_config(self) -> None:
        config = ReviewConfig(mode="files", target_files=["a.py", "b.py"])
        assert config.target_files == ["a.py", "b.py"]
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
            "license_compliance",
            "release_hygiene",
        }
```

Update `test_post_feature_config`:
```python
    def test_post_feature_config(self) -> None:
        config = ReviewConfig(mode="post_feature", spec_path="docs/plan.md")
        assert config.spec_path == "docs/plan.md"
        assert config.audit_tools == {
            "ruff",
            "pyright",
            "pytest",
            "secrets",
            "coverage",
            "license_compliance",
            "release_hygiene",
        }
```

- [ ] **Step 13: Run all composition and mechanical tests**

Run: `uv run pytest tests/test_compositions.py tests/test_mechanical_phase.py -v`
Expected: ALL PASS

- [ ] **Step 14: Commit**

```bash
git add codemonkeys/workflows/phase_library/mechanical.py codemonkeys/workflows/compositions.py tests/test_mechanical_phase.py tests/test_compositions.py
git commit -m "feat: wire license compliance and release hygiene into audit dispatch and compositions"
```

---

### Task 5: Create `RESILIENCE_REVIEW` prompt template

**Files:**
- Create: `codemonkeys/core/prompts/resilience_review.py`
- Modify: `codemonkeys/core/prompts/__init__.py`
- Test: `tests/test_resilience_review_prompt.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_resilience_review_prompt.py`:

```python
from __future__ import annotations

from codemonkeys.core.prompts import RESILIENCE_REVIEW


class TestResilienceReviewPrompt:
    def test_is_nonempty_string(self) -> None:
        assert isinstance(RESILIENCE_REVIEW, str)
        assert len(RESILIENCE_REVIEW) > 100

    def test_has_all_checklist_categories(self) -> None:
        expected_categories = [
            "concurrency",
            "error_recovery",
            "log_hygiene",
        ]
        for category in expected_categories:
            assert category in RESILIENCE_REVIEW, f"Missing category: {category}"

    def test_has_exclusions_section(self) -> None:
        assert "Exclusions" in RESILIENCE_REVIEW

    def test_mentions_asyncio_gather(self) -> None:
        assert "asyncio.gather" in RESILIENCE_REVIEW

    def test_mentions_timeout(self) -> None:
        assert "timeout" in RESILIENCE_REVIEW.lower()

    def test_mentions_log_level(self) -> None:
        assert "log level" in RESILIENCE_REVIEW.lower() or "log_level" in RESILIENCE_REVIEW.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resilience_review_prompt.py -v`
Expected: FAIL with `ImportError: cannot import name 'RESILIENCE_REVIEW'`

- [ ] **Step 3: Create `resilience_review.py` prompt template**

Create `codemonkeys/core/prompts/resilience_review.py`:

```python
"""Production resilience checklist — concurrency, error recovery, and log hygiene."""

RESILIENCE_REVIEW = """\
## Resilience Review Checklist

Review the file for production resilience issues. Only report findings at 80%+
confidence with concrete scenarios where the issue would cause a problem.

### concurrency

- Missing `await` on coroutine calls (returns a coroutine object instead of the result)
- Shared mutable state across async tasks — module-level dicts/lists mutated in coroutines
- `asyncio.gather` without `return_exceptions=True` where one failure should not kill siblings
- Synchronous blocking calls inside async functions — `time.sleep`, blocking I/O, \
`subprocess.run` without an executor
- Missing cancellation handling — `asyncio.CancelledError` caught and swallowed instead \
of propagated
- Thread-unsafe operations without locks — shared state mutated from multiple threads
- Check-then-act race conditions (TOCTOU) — file existence checks followed by open, \
key checks followed by access

### error_recovery

- I/O operations (HTTP, file, DB) without timeout configuration
- Missing retry logic on transient failures (network calls, rate-limited APIs)
- No backoff on repeated failures to the same service
- Resource leaks on error paths — connections or file handles not closed in `finally` \
or context manager
- Cascading failure risk — one downstream service failure takes out the whole request

### log_hygiene

- Error/exception paths that don't log — silent failures
- Log messages missing context — no relevant IDs, operation name, or input state
- Sensitive data in log output — passwords, tokens, PII
- Wrong log level — errors logged as `info`, debug noise at `warning`
- Bare `logger.exception()` without a descriptive message

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Broad exception catching (CODE_QUALITY owns this)
- Missing exception handling (CODE_QUALITY owns this)
- General try/except patterns (CODE_QUALITY owns this)
- PII as a security vulnerability (SECURITY_OBSERVATIONS owns this — report here \
only as an operational log hygiene concern)"""
```

- [ ] **Step 4: Add to `prompts/__init__.py`**

In `codemonkeys/core/prompts/__init__.py`, add import:
```python
from codemonkeys.core.prompts.resilience_review import RESILIENCE_REVIEW
```

Add `"RESILIENCE_REVIEW"` to `__all__` list.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_resilience_review_prompt.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/core/prompts/resilience_review.py codemonkeys/core/prompts/__init__.py tests/test_resilience_review_prompt.py
git commit -m "feat: add RESILIENCE_REVIEW prompt template"
```

---

### Task 6: Create `TEST_QUALITY` prompt template

**Files:**
- Create: `codemonkeys/core/prompts/test_quality.py`
- Modify: `codemonkeys/core/prompts/__init__.py`
- Test: `tests/test_test_quality_prompt.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_test_quality_prompt.py`:

```python
from __future__ import annotations

from codemonkeys.core.prompts import TEST_QUALITY


class TestTestQualityPrompt:
    def test_is_nonempty_string(self) -> None:
        assert isinstance(TEST_QUALITY, str)
        assert len(TEST_QUALITY) > 100

    def test_has_all_checklist_categories(self) -> None:
        expected_categories = [
            "assertion_quality",
            "test_design",
            "isolation",
        ]
        for category in expected_categories:
            assert category in TEST_QUALITY, f"Missing category: {category}"

    def test_has_exclusions_section(self) -> None:
        assert "Exclusions" in TEST_QUALITY

    def test_mentions_tautological(self) -> None:
        assert "tautological" in TEST_QUALITY.lower() or "assert True" in TEST_QUALITY

    def test_mentions_mock(self) -> None:
        assert "mock" in TEST_QUALITY.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_test_quality_prompt.py -v`
Expected: FAIL with `ImportError: cannot import name 'TEST_QUALITY'`

- [ ] **Step 3: Create `test_quality.py` prompt template**

Create `codemonkeys/core/prompts/test_quality.py`:

```python
"""Test quality checklist — assertion rigor, test design, and isolation."""

TEST_QUALITY = """\
## Test Quality Review Checklist

Review the test file for quality issues. Only report findings at 80%+ confidence.

### assertion_quality

- Assert-free tests — test runs code but never asserts on the result
- Tautological assertions — `assert True`, `assert x == x`, \
`assert isinstance(obj, object)`
- Assertions only on type, never on value — `assert isinstance(result, dict)` \
without checking content
- Over-reliance on `mock.assert_called_once()` without verifying what was passed \
or what was returned
- Asserting on string representations instead of structured data

### test_design

- Test name doesn't match what's actually being tested
- Single test covering multiple unrelated behaviors — should be split
- Test duplicates implementation logic — reconstructs expected value using the \
same algorithm as the code under test
- Fixtures or setup that does real work the test should be verifying
- Tests that only exercise the happy path — no edge cases, no error inputs

### isolation

- Tests that depend on execution order — shared mutable state between test functions
- Tests that hit the network, filesystem, or external services without mocking \
(unintentional integration tests)
- Tests that modify module-level or class-level state without cleanup

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Test coverage gaps (mechanical coverage tool owns this)
- Test framework conventions and naming style (style, not quality)
- Missing tests for specific functions (that's coverage, not quality)"""
```

- [ ] **Step 4: Add to `prompts/__init__.py`**

In `codemonkeys/core/prompts/__init__.py`, add import:
```python
from codemonkeys.core.prompts.test_quality import TEST_QUALITY
```

Add `"TEST_QUALITY"` to `__all__` list.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_test_quality_prompt.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/core/prompts/test_quality.py codemonkeys/core/prompts/__init__.py tests/test_test_quality_prompt.py
git commit -m "feat: add TEST_QUALITY prompt template"
```

---

### Task 7: Wire prompt templates into file reviewer agent

**Files:**
- Modify: `codemonkeys/core/agents/python_file_reviewer.py`
- Test: `tests/test_review_phases.py`

- [ ] **Step 1: Write failing test for resilience parameter**

Add to `tests/test_review_phases.py`:

```python
class TestFileReviewerPromptInjection:
    def test_resilience_flag_injects_prompt(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["app.py"], resilience=True)
        assert "concurrency" in agent.prompt
        assert "error_recovery" in agent.prompt
        assert "log_hygiene" in agent.prompt

    def test_resilience_off_by_default(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["app.py"])
        assert "Resilience Review" not in agent.prompt

    def test_test_quality_flag_injects_prompt(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["test_app.py"], test_quality=True)
        assert "assertion_quality" in agent.prompt
        assert "test_design" in agent.prompt
        assert "isolation" in agent.prompt

    def test_test_quality_off_by_default(self) -> None:
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        agent = make_python_file_reviewer(["test_app.py"])
        assert "Test Quality" not in agent.prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_phases.py::TestFileReviewerPromptInjection -v`
Expected: FAIL — `make_python_file_reviewer` doesn't accept `resilience` or `test_quality` parameters

- [ ] **Step 3: Update `make_python_file_reviewer` to accept new parameters**

In `codemonkeys/core/agents/python_file_reviewer.py`:

Update imports:
```python
from codemonkeys.core.prompts import (
    CODE_QUALITY,
    PYTHON_GUIDELINES,
    RESILIENCE_REVIEW,
    SECURITY_OBSERVATIONS,
    TEST_QUALITY,
)
```

Update function signature and body:
```python
def make_python_file_reviewer(
    files: list[str],
    *,
    model: str = "sonnet",
    resilience: bool = False,
    test_quality: bool = False,
) -> AgentDefinition:
    """Create a reviewer agent for one or more Python files."""
    file_list = "\n".join(f"- `{f}`" for f in files)

    checklists = f"{CODE_QUALITY}\n\n{SECURITY_OBSERVATIONS}\n\n{PYTHON_GUIDELINES}"
    if resilience:
        checklists += f"\n\n{RESILIENCE_REVIEW}"
    if test_quality:
        checklists += f"\n\n{TEST_QUALITY}"

    return AgentDefinition(
        description=f"Review {len(files)} file(s) for quality and security",
        prompt=f"""\
You review Python files for code quality and security issues. Read each file
listed below, apply the checklists, then return your findings as structured JSON.

## Files to Review

{file_list}

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping — just
the JSON:

{{
  "results": [
    {{
      "file": "<exact path from the list above>",
      "summary": "<one sentence describing what this file does>",
      "findings": [
        {{
          "file": "<path>",
          "line": <int or null>,
          "severity": "<high|medium|low|info>",
          "category": "<quality|security>",
          "subcategory": "<specific check name>",
          "title": "<short one-line summary>",
          "description": "<what's wrong>",
          "suggestion": "<how to fix it, or null>"
        }}
      ]
    }}
  ]
}}

## Rules

- Review EACH file listed above — read all of them
- Include an entry in "results" for every file, even if it has no issues
- Only report findings at 80%+ confidence
- `line` is null only when the finding is about something missing or file-wide
- `category` is either `quality` or `security`
- `subcategory` must match one of the checklist headings below
- If a file has no issues, include it with an empty findings array
- Do NOT report formatting issues (linter handles those) or type errors (type checker handles those)
- Do NOT read files other than those listed above

{checklists}""",
        model=model,
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_phases.py::TestFileReviewerPromptInjection -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/core/agents/python_file_reviewer.py tests/test_review_phases.py
git commit -m "feat: add resilience and test_quality flags to file reviewer agent"
```

---

### Task 8: Wire prompt injection into `file_review` phase

**Files:**
- Modify: `codemonkeys/workflows/phase_library/review.py:44-121`
- Test: `tests/test_review_phases.py`

- [ ] **Step 1: Write failing test for resilience injection in thorough modes**

Add to `tests/test_review_phases.py` inside `TestFileReview`:

```python
    @pytest.mark.asyncio
    async def test_passes_resilience_in_full_repo_mode(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="full_repo",
            phase_results={"discover": {"files": ["app.py"], "structural_metadata": ""}},
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ), patch(
            "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
        ) as mock_make:
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        mock_make.assert_called_once()
        call_kwargs = mock_make.call_args
        assert call_kwargs.kwargs.get("resilience") is True

    @pytest.mark.asyncio
    async def test_no_resilience_in_diff_mode(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="diff",
            phase_results={
                "discover": {
                    "files": ["app.py"],
                    "structural_metadata": "",
                    "diff_hunks": "",
                    "call_graph": "",
                },
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ), patch(
            "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
        ) as mock_make:
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        call_kwargs = mock_make.call_args
        assert call_kwargs.kwargs.get("resilience") is False

    @pytest.mark.asyncio
    async def test_passes_test_quality_for_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(
            return_value=RunResult(
                text="{}",
                structured=FileFindings(
                    file="test_app.py", summary="test", findings=[]
                ).model_dump(),
                usage={"input_tokens": 100, "output_tokens": 50},
                cost=None,
                duration_ms=500,
            )
        )

        ctx = _make_ctx(
            tmp_path,
            mode="files",
            phase_results={
                "discover": {"files": ["test_app.py"], "structural_metadata": ""},
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ), patch(
            "codemonkeys.workflows.phase_library.review.make_python_file_reviewer"
        ) as mock_make:
            mock_make.return_value = MagicMock()
            await file_review(ctx)

        call_kwargs = mock_make.call_args
        assert call_kwargs.kwargs.get("test_quality") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_phases.py::TestFileReview::test_passes_resilience_in_full_repo_mode tests/test_review_phases.py::TestFileReview::test_no_resilience_in_diff_mode tests/test_review_phases.py::TestFileReview::test_passes_test_quality_for_test_files -v`
Expected: FAIL — `make_python_file_reviewer` not called with `resilience` or `test_quality`

- [ ] **Step 3: Update `_run_file_batch` and `file_review` to pass new parameters**

In `codemonkeys/workflows/phase_library/review.py`:

Update `_run_file_batch` signature to accept the new flags:

```python
async def _run_file_batch(
    batch_files: list[str],
    model: str,
    ctx: WorkflowContext,
    semaphore: asyncio.Semaphore,
    *,
    resilience: bool = False,
    test_quality: bool = False,
) -> FileFindings:
    """Run a single file review batch under the concurrency semaphore."""
    async with semaphore:
        config = ctx.config
        runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
        agent = make_python_file_reviewer(
            batch_files, model=model, resilience=resilience, test_quality=test_quality
        )
```

(rest of the function stays the same)

Update `file_review` to compute and pass the flags:

```python
async def file_review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    """Batch files, dispatch per-file reviewers in parallel (haiku for tests, sonnet for prod)."""
    files: list[str] = ctx.phase_results["discover"]["files"]
    config = ctx.config

    resilience = config.mode in ("full_repo", "post_feature")

    batches: list[tuple[list[str], str, bool]] = []  # (files, model, is_test)
    test_batch: list[str] = []
    prod_batch: list[str] = []

    for f in files:
        if "test" in f.split("/")[-1]:
            test_batch.append(f)
            if len(test_batch) == 3:
                batches.append((test_batch, "haiku", True))
                test_batch = []
        else:
            prod_batch.append(f)
            if len(prod_batch) == 3:
                batches.append((prod_batch, "sonnet", False))
                prod_batch = []

    if test_batch:
        batches.append((test_batch, "haiku", True))
    if prod_batch:
        batches.append((prod_batch, "sonnet", False))

    semaphore = asyncio.Semaphore(config.max_concurrent)
    tasks = [
        _run_file_batch(
            batch_files,
            model,
            ctx,
            semaphore,
            resilience=resilience and not is_test,
            test_quality=is_test,
        )
        for batch_files, model, is_test in batches
    ]
    all_findings = await asyncio.gather(*tasks)

    return {"file_findings": list(all_findings)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_phases.py::TestFileReview -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/workflows/phase_library/review.py tests/test_review_phases.py
git commit -m "feat: wire resilience and test quality prompts into file review phase"
```

---

### Task 9: Add `pip-licenses` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `pip-licenses` to the `python` optional dependency group**

In `pyproject.toml`, update the `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
python = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pip-audit>=2.7",
    "pip-licenses>=5.0",
    "ruff>=0.5,<1",
]
```

- [ ] **Step 2: Install the updated dependencies**

Run: `uv sync --extra dev`
Expected: `pip-licenses` installed successfully

- [ ] **Step 3: Verify pip-licenses works**

Run: `uv run pip-licenses --format=json | head -5`
Expected: JSON output with package license data

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add pip-licenses dependency for license compliance tool"
```

---

### Task 10: Run full linting, type checking, and test suite

**Files:** None (validation only)

- [ ] **Step 1: Run ruff linter**

Run: `uv run ruff check .`
Expected: No errors (or fix any that appear)

- [ ] **Step 2: Run ruff formatter**

Run: `uv run ruff format --check .`
Expected: All files formatted

- [ ] **Step 3: Run pyright**

Run: `uv run pyright .`
Expected: No errors

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Fix any issues and commit**

If any issues found:
```bash
uv run ruff check --fix . && uv run ruff format .
git add -A
git commit -m "fix: resolve lint/type/test issues from pipeline hardening"
```
