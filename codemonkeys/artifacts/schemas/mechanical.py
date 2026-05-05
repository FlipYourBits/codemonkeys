"""Schemas for mechanical audit tool results (ruff, pyright, pytest, pip-audit, secrets, coverage, dead code)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RuffFinding(BaseModel):
    file: str = Field(description="Relative path to the file with the lint violation")
    line: int = Field(description="Line number where the violation occurs")
    code: str = Field(description="Ruff rule code (e.g., 'E501', 'F401')")
    message: str = Field(description="Human-readable description of the violation")


class PyrightFinding(BaseModel):
    file: str = Field(description="Relative path to the file with the type error")
    line: int = Field(description="Line number where the type error occurs")
    severity: Literal["error", "warning", "information"] = Field(
        description="Pyright diagnostic severity level"
    )
    message: str = Field(description="Human-readable description of the type error")


class PytestResult(BaseModel):
    passed: int = Field(description="Number of tests that passed")
    failed: int = Field(description="Number of tests that failed")
    errors: int = Field(
        description="Number of tests that errored during collection or execution"
    )
    failures: list[str] = Field(
        description="List of failed test identifiers (e.g., 'tests/test_foo.py::test_bar')"
    )


class CveFinding(BaseModel):
    package: str = Field(description="Name of the vulnerable package")
    installed_version: str = Field(
        description="Currently installed version of the package"
    )
    fixed_version: str | None = Field(
        description="Version that fixes the vulnerability, or null if no fix is available"
    )
    cve_id: str = Field(description="CVE identifier (e.g., 'CVE-2024-1234')")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        description="CVSS-based severity rating of the vulnerability"
    )
    description: str = Field(description="Brief description of the vulnerability")


class SecretsFinding(BaseModel):
    file: str = Field(description="Relative path to the file containing the secret")
    line: int = Field(description="Line number where the secret was detected")
    pattern: str = Field(
        description="Pattern or rule that matched (e.g., 'aws-access-key')"
    )
    snippet: str = Field(
        description="Redacted snippet showing the detected secret context"
    )


class CoverageMap(BaseModel):
    covered: list[str] = Field(description="List of file paths that have test coverage")
    uncovered: list[str] = Field(
        description="List of file paths that lack test coverage"
    )


class DeadCodeFinding(BaseModel):
    file: str = Field(description="Relative path to the file containing dead code")
    line: int = Field(description="Line number where the dead code is defined")
    name: str = Field(description="Name of the unused symbol")
    kind: Literal["function", "class", "import"] = Field(
        description="Kind of dead code (function, class, or import)"
    )


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
