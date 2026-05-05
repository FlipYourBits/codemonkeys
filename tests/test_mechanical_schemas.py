from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)


class TestRuffFinding:
    def test_roundtrip_json(self) -> None:
        finding = RuffFinding(
            file="src/utils.py",
            line=10,
            code="F401",
            message="'os' imported but unused",
        )
        data = json.loads(finding.model_dump_json())
        restored = RuffFinding.model_validate(data)
        assert restored == finding

    def test_json_schema_has_descriptions(self) -> None:
        schema = RuffFinding.model_json_schema()
        for field_name in ("file", "line", "code", "message"):
            assert "description" in schema["properties"][field_name]

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            RuffFinding(file="src/utils.py", line=10, code="F401")  # type: ignore[call-arg]


class TestPyrightFinding:
    def test_roundtrip_json(self) -> None:
        finding = PyrightFinding(
            file="src/auth.py",
            line=55,
            severity="error",
            message="Cannot assign type 'str' to type 'int'",
        )
        data = json.loads(finding.model_dump_json())
        restored = PyrightFinding.model_validate(data)
        assert restored == finding

    def test_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            PyrightFinding(
                file="src/auth.py",
                line=55,
                severity="critical",  # type: ignore[arg-type]
                message="Bad type",
            )

    def test_json_schema_has_descriptions(self) -> None:
        schema = PyrightFinding.model_json_schema()
        for field_name in ("file", "line", "severity", "message"):
            assert "description" in schema["properties"][field_name]


class TestPytestResult:
    def test_roundtrip_json(self) -> None:
        result = PytestResult(
            passed=45,
            failed=2,
            errors=1,
            failures=[
                "tests/test_auth.py::test_login",
                "tests/test_auth.py::test_logout",
            ],
        )
        data = json.loads(result.model_dump_json())
        restored = PytestResult.model_validate(data)
        assert restored == result

    def test_empty_failures_list(self) -> None:
        result = PytestResult(passed=50, failed=0, errors=0, failures=[])
        assert result.failures == []

    def test_json_schema_has_descriptions(self) -> None:
        schema = PytestResult.model_json_schema()
        for field_name in ("passed", "failed", "errors", "failures"):
            assert "description" in schema["properties"][field_name]


class TestCveFinding:
    def test_roundtrip_json(self) -> None:
        finding = CveFinding(
            package="requests",
            installed_version="2.25.0",
            fixed_version="2.31.0",
            cve_id="CVE-2023-32681",
            severity="high",
            description="Unintended leak of Proxy-Authorization header.",
        )
        data = json.loads(finding.model_dump_json())
        restored = CveFinding.model_validate(data)
        assert restored == finding

    def test_fixed_version_null(self) -> None:
        finding = CveFinding(
            package="legacy-lib",
            installed_version="1.0.0",
            fixed_version=None,
            cve_id="CVE-2024-9999",
            severity="critical",
            description="No fix available.",
        )
        assert finding.fixed_version is None

    def test_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            CveFinding(
                package="foo",
                installed_version="1.0.0",
                fixed_version=None,
                cve_id="CVE-2024-0001",
                severity="info",  # type: ignore[arg-type]
                description="Bad severity.",
            )

    def test_json_schema_has_descriptions(self) -> None:
        schema = CveFinding.model_json_schema()
        for field_name in (
            "package",
            "installed_version",
            "fixed_version",
            "cve_id",
            "severity",
            "description",
        ):
            assert "description" in schema["properties"][field_name]


class TestSecretsFinding:
    def test_roundtrip_json(self) -> None:
        finding = SecretsFinding(
            file="config/settings.py",
            line=12,
            pattern="aws-access-key",
            snippet="AWS_KEY = 'AKIA***REDACTED***'",
        )
        data = json.loads(finding.model_dump_json())
        restored = SecretsFinding.model_validate(data)
        assert restored == finding

    def test_json_schema_has_descriptions(self) -> None:
        schema = SecretsFinding.model_json_schema()
        for field_name in ("file", "line", "pattern", "snippet"):
            assert "description" in schema["properties"][field_name]


class TestCoverageMap:
    def test_roundtrip_json(self) -> None:
        coverage = CoverageMap(
            covered=["src/auth.py", "src/utils.py"],
            uncovered=["src/legacy.py"],
        )
        data = json.loads(coverage.model_dump_json())
        restored = CoverageMap.model_validate(data)
        assert restored == coverage

    def test_empty_lists(self) -> None:
        coverage = CoverageMap(covered=[], uncovered=[])
        assert coverage.covered == []
        assert coverage.uncovered == []

    def test_json_schema_has_descriptions(self) -> None:
        schema = CoverageMap.model_json_schema()
        for field_name in ("covered", "uncovered"):
            assert "description" in schema["properties"][field_name]


class TestDeadCodeFinding:
    def test_roundtrip_json(self) -> None:
        finding = DeadCodeFinding(
            file="src/helpers.py",
            line=88,
            name="unused_helper",
            kind="function",
        )
        data = json.loads(finding.model_dump_json())
        restored = DeadCodeFinding.model_validate(data)
        assert restored == finding

    def test_invalid_kind(self) -> None:
        with pytest.raises(ValidationError):
            DeadCodeFinding(
                file="src/helpers.py",
                line=88,
                name="unused_helper",
                kind="variable",  # type: ignore[arg-type]
            )

    def test_json_schema_has_descriptions(self) -> None:
        schema = DeadCodeFinding.model_json_schema()
        for field_name in ("file", "line", "name", "kind"):
            assert "description" in schema["properties"][field_name]


class TestMechanicalAuditResult:
    def test_roundtrip_json(self) -> None:
        result = MechanicalAuditResult(
            ruff=[
                RuffFinding(
                    file="src/app.py", line=1, code="F401", message="Unused import"
                ),
            ],
            pyright=[
                PyrightFinding(
                    file="src/app.py",
                    line=20,
                    severity="error",
                    message="Type mismatch",
                ),
            ],
            pytest=PytestResult(
                passed=10, failed=1, errors=0, failures=["tests/test_app.py::test_main"]
            ),
            pip_audit=[
                CveFinding(
                    package="urllib3",
                    installed_version="1.26.5",
                    fixed_version="1.26.18",
                    cve_id="CVE-2023-45803",
                    severity="medium",
                    description="Request body not stripped on redirect.",
                ),
            ],
            secrets=[
                SecretsFinding(
                    file=".env",
                    line=3,
                    pattern="generic-api-key",
                    snippet="API_KEY=sk-***REDACTED***",
                ),
            ],
            coverage=CoverageMap(
                covered=["src/app.py"],
                uncovered=["src/legacy.py"],
            ),
            dead_code=[
                DeadCodeFinding(
                    file="src/legacy.py", line=5, name="OldClass", kind="class"
                ),
            ],
        )
        data = json.loads(result.model_dump_json())
        restored = MechanicalAuditResult.model_validate(data)
        assert restored == result

    def test_nullable_fields(self) -> None:
        result = MechanicalAuditResult(
            ruff=[],
            pyright=[],
            pytest=None,
            pip_audit=None,
            secrets=[],
            coverage=None,
            dead_code=None,
        )
        assert result.pytest is None
        assert result.pip_audit is None
        assert result.coverage is None
        assert result.dead_code is None

    def test_json_schema_has_descriptions(self) -> None:
        schema = MechanicalAuditResult.model_json_schema()
        for field_name in (
            "ruff",
            "pyright",
            "pytest",
            "pip_audit",
            "secrets",
            "coverage",
            "dead_code",
        ):
            assert "description" in schema["properties"][field_name]
