from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult


class TestFinding:
    def test_roundtrip_json(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection via f-string",
            description="User input interpolated into SQL query without parameterization.",
            suggestion="Use parameterized query: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
        )
        data = json.loads(finding.model_dump_json())
        restored = Finding.model_validate(data)
        assert restored == finding

    def test_line_is_optional(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=None,
            severity="low",
            category="quality",
            subcategory="documentation",
            title="Missing module docstring",
            description="Module has no docstring.",
            suggestion=None,
        )
        assert finding.line is None
        assert finding.suggestion is None

    def test_json_schema_has_descriptions(self) -> None:
        schema = Finding.model_json_schema()
        assert "description" in schema["properties"]["file"]
        assert "description" in schema["properties"]["severity"]
        assert "description" in schema["properties"]["category"]


class TestFileFindings:
    def test_from_findings_list(self) -> None:
        findings = FileFindings(
            file="src/auth.py",
            summary="Authentication module with SQL injection vulnerability.",
            findings=[
                Finding(
                    file="src/auth.py",
                    line=42,
                    severity="high",
                    category="security",
                    subcategory="injection",
                    title="SQL injection",
                    description="Unsafe query.",
                    suggestion="Use parameterized queries.",
                ),
            ],
        )
        assert len(findings.findings) == 1
        data = json.loads(findings.model_dump_json())
        assert data["file"] == "src/auth.py"


class TestFixRequest:
    def test_selected_findings(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection",
            description="Unsafe query.",
            suggestion="Use parameterized queries.",
        )
        request = FixRequest(file="src/auth.py", findings=[finding])
        data = json.loads(request.model_dump_json())
        assert len(data["findings"]) == 1


class TestFeaturePlan:
    def test_roundtrip(self) -> None:
        plan = FeaturePlan(
            title="Add user authentication",
            description="Implement JWT-based auth with login/logout endpoints.",
            steps=[
                PlanStep(
                    description="Create auth middleware",
                    files=["src/middleware/auth.py"],
                ),
                PlanStep(
                    description="Add login endpoint",
                    files=["src/routes/auth.py", "tests/test_auth.py"],
                ),
            ],
        )
        data = json.loads(plan.model_dump_json())
        restored = FeaturePlan.model_validate(data)
        assert len(restored.steps) == 2
        assert restored.title == "Add user authentication"


class TestFixResult:
    def test_roundtrip(self) -> None:
        result = FixResult(
            file="src/auth.py",
            fixed=["SQL injection on line 42"],
            skipped=["Could not resolve ambiguous suggestion on line 88"],
        )
        data = json.loads(result.model_dump_json())
        restored = FixResult.model_validate(data)
        assert len(restored.fixed) == 1
        assert len(restored.skipped) == 1


class TestVerificationResult:
    def test_roundtrip(self) -> None:
        result = VerificationResult(
            tests_passed=True,
            lint_passed=True,
            typecheck_passed=False,
            errors=["pyright: src/auth.py:42 — missing return type"],
        )
        data = json.loads(result.model_dump_json())
        restored = VerificationResult.model_validate(data)
        assert restored.tests_passed is True
        assert restored.typecheck_passed is False
