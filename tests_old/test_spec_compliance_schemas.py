from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.spec_compliance import (
    SpecComplianceFinding,
    SpecComplianceFindings,
)


class TestSpecComplianceFinding:
    def test_roundtrip_json(self) -> None:
        finding = SpecComplianceFinding(
            category="completeness",
            severity="high",
            spec_step="Add login endpoint",
            files=["src/routes/auth.py"],
            title="Login endpoint not implemented",
            description="The spec requires a POST /login endpoint but it was not created.",
            suggestion="Create the endpoint in src/routes/auth.py",
        )
        data = json.loads(finding.model_dump_json())
        restored = SpecComplianceFinding.model_validate(data)
        assert restored == finding

    def test_nullable_spec_step(self) -> None:
        finding = SpecComplianceFinding(
            category="scope_creep",
            severity="low",
            spec_step=None,
            files=["src/utils.py"],
            title="Extra utility module added",
            description="A utility module was added that is not part of the spec.",
        )
        assert finding.spec_step is None

    def test_nullable_suggestion(self) -> None:
        finding = SpecComplianceFinding(
            category="test_coverage",
            severity="medium",
            spec_step="Write unit tests",
            files=["tests/test_auth.py"],
            title="Missing edge case test",
            description="No test for expired token handling.",
            suggestion=None,
        )
        assert finding.suggestion is None

    def test_all_category_literals(self) -> None:
        categories = [
            "completeness",
            "scope_creep",
            "contract_compliance",
            "behavioral_fidelity",
            "test_coverage",
        ]
        for cat in categories:
            finding = SpecComplianceFinding(
                category=cat,
                severity="low",
                spec_step=None,
                files=["src/foo.py"],
                title=f"Test {cat}",
                description=f"Testing category {cat}.",
            )
            assert finding.category == cat

    def test_json_schema_has_descriptions(self) -> None:
        schema = SpecComplianceFinding.model_json_schema()
        assert "description" in schema["properties"]["category"]
        assert "description" in schema["properties"]["severity"]
        assert "description" in schema["properties"]["spec_step"]
        assert "description" in schema["properties"]["files"]
        assert "description" in schema["properties"]["title"]
        assert "description" in schema["properties"]["description"]
        assert "description" in schema["properties"]["suggestion"]


class TestSpecComplianceFindings:
    def test_roundtrip_json(self) -> None:
        findings = SpecComplianceFindings(
            spec_title="Add user authentication",
            steps_implemented=3,
            steps_total=5,
            findings=[
                SpecComplianceFinding(
                    category="completeness",
                    severity="high",
                    spec_step="Add login endpoint",
                    files=["src/routes/auth.py"],
                    title="Login endpoint not implemented",
                    description="The spec requires a POST /login endpoint.",
                    suggestion="Create the endpoint.",
                ),
            ],
        )
        data = json.loads(findings.model_dump_json())
        restored = SpecComplianceFindings.model_validate(data)
        assert restored == findings
        assert restored.steps_implemented == 3
        assert restored.steps_total == 5

    def test_empty_findings_list(self) -> None:
        findings = SpecComplianceFindings(
            spec_title="Simple refactor",
            steps_implemented=2,
            steps_total=2,
        )
        assert findings.findings == []

    def test_json_schema_has_descriptions(self) -> None:
        schema = SpecComplianceFindings.model_json_schema()
        assert "description" in schema["properties"]["spec_title"]
        assert "description" in schema["properties"]["steps_implemented"]
        assert "description" in schema["properties"]["steps_total"]
        assert "description" in schema["properties"]["findings"]
