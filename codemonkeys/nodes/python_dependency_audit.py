"""Audit Python dependencies for known CVEs via pip-audit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from codemonkeys.models import HAIKU_4_5
from codemonkeys.nodes.base import ClaudeAgentNode


class DependencyAuditFinding(BaseModel):
    file: str = Field(examples=["pyproject.toml"])
    line: int = Field(examples=[1])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: CVSS >= 7.0, or known active exploitation. MEDIUM: CVSS 4.0-6.9, or limited exploitability. LOW: CVSS < 4.0, disputed, or withdrawn advisory."
    )
    category: str = Field(examples=["vulnerable_dependency"])
    source: str = Field(examples=["python_dependency_audit"])
    description: str = Field(
        examples=["requests 2.28.0 has CVE-2023-XXXXX (CVSS 9.1)."]
    )
    recommendation: str = Field(examples=["Upgrade to requests>=2.31.0."])
    confidence: Literal["high", "medium", "low"] = Field(
        description="high: confirmed CVE from pip-audit. medium: advisory with caveats. low: disputed or withdrawn."
    )


class DependencyAuditOutput(BaseModel):
    findings: list[DependencyAuditFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"packages_scanned": 45, "high": 1, "medium": 0, "low": 0}],
    )


_SKILL = """\
# Dependency audit

Audit Python dependencies for known vulnerabilities
using pip-audit. Report findings only — never fix,
upgrade, or modify any packages.

## Scope

Scan all installed packages in the project virtualenv
for known CVEs.

## Method

1. Run `pip-audit --format json --strict --desc` to scan
   for known vulnerabilities with machine-readable output.
   Never pass `--fix` or any flag that modifies packages.
2. If pip-audit is not available, report a single finding
   with category `missing_tooling` and severity `MEDIUM`.
   Do not attempt to check dependencies manually.
3. Parse the JSON output. For each vulnerability: identify
   the affected package, installed version, CVE ID, CVSS
   score (if available), and the fixed version.
4. Cross-reference the package against pyproject.toml or
   requirements files to identify the pinned line number.

## Categories

### `vulnerable_dependency`
- Package with a known CVE
- Package pinned to an affected version range

### `missing_tooling`
- pip-audit is not installed (cannot complete audit)

### `scan_error`
- pip-audit failed due to network error, broken virtualenv,
  or other infrastructure issue (not a found CVE)

## Triage

- Only report confirmed CVEs from pip-audit output.
- Do not speculate about vulnerabilities from memory.
- Deduplicate — one finding per CVE per package.

## Exclusions — DO NOT REPORT

- Code quality or style issues (code review owns these)
- Security issues in application code (security audit
  owns these)
- Test failures (test node owns these)
- Documentation drift (docs review owns these)"""


class PythonDependencyAudit(ClaudeAgentNode):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("model", HAIKU_4_5)
        super().__init__(
            name="python_dependency_audit",
            output=DependencyAuditOutput,
            system_prompt=_SKILL,
            prompt_template="Audit Python dependencies for known vulnerabilities.",
            allow=[
                "Read",
                "Glob",
                "Grep",
                "Bash(pip-audit*)",
                "Bash(pip list*)",
                "Bash(pip show*)",
            ],
            deny=[
                "Bash(pip install*)",
                "Bash(pip uninstall*)",
                "Bash(pip-audit*--fix*)",
                "Bash(python*)",
                "Bash(pytest*)",
            ],
            on_unmatched="deny",
            **kwargs,
        )
