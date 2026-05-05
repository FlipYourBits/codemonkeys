# tests/test_architecture_schemas.py
from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.architecture import (
    ArchitectureFinding,
    ArchitectureFindings,
)


class TestArchitectureFinding:
    def test_roundtrip_json(self) -> None:
        finding = ArchitectureFinding(
            files=["src/services/prices.py", "src/feeds/price_feed.py"],
            severity="high",
            category="design",
            subcategory="communication_mismatch",
            title="Price data served via both HTTP polling and WebSocket",
            description="prices.py polls an HTTP endpoint every 10s while price_feed.py uses a WebSocket for the same data source.",
            suggestion="Consolidate to a single transport — use the WebSocket feed and have prices.py subscribe to it.",
        )
        data = json.loads(finding.model_dump_json())
        restored = ArchitectureFinding.model_validate(data)
        assert restored == finding

    def test_files_is_a_list(self) -> None:
        finding = ArchitectureFinding(
            files=["a.py", "b.py", "c.py"],
            severity="medium",
            category="design",
            subcategory="paradigm_inconsistency",
            title="Mixed paradigms for route handlers",
            description="a.py and b.py use functions, c.py uses a class.",
            suggestion=None,
        )
        assert len(finding.files) == 3

    def test_suggestion_is_optional(self) -> None:
        finding = ArchitectureFinding(
            files=["x.py"],
            severity="low",
            category="design",
            subcategory="dependency_coupling",
            title="Everything imports utils",
            description="utils.py is imported by every module.",
            suggestion=None,
        )
        assert finding.suggestion is None

    def test_json_schema_has_descriptions(self) -> None:
        schema = ArchitectureFinding.model_json_schema()
        assert "description" in schema["properties"]["files"]
        assert "description" in schema["properties"]["severity"]


class TestArchitectureFindings:
    def test_roundtrip_json(self) -> None:
        findings = ArchitectureFindings(
            files_reviewed=["a.py", "b.py"],
            findings=[
                ArchitectureFinding(
                    files=["a.py", "b.py"],
                    severity="medium",
                    category="design",
                    subcategory="interface_inconsistency",
                    title="Inconsistent return types",
                    description="a.py returns dicts, b.py returns Pydantic models for the same data.",
                    suggestion="Standardize on Pydantic models.",
                ),
            ],
        )
        data = json.loads(findings.model_dump_json())
        restored = ArchitectureFindings.model_validate(data)
        assert len(restored.findings) == 1
        assert restored.files_reviewed == ["a.py", "b.py"]

    def test_empty_findings(self) -> None:
        findings = ArchitectureFindings(
            files_reviewed=["a.py"],
            findings=[],
        )
        assert len(findings.findings) == 0
