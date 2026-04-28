from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from agentpipe.nodes.resolve_findings import (
    ResolveFindings,
    ResolveOutput,
    _extract_items_from_state,
    _format_findings,
    _select_by_input,
)


class FakeUpstreamFinding(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    source: str = ""
    description: str = ""


class FakeUpstreamOutput(BaseModel):
    findings: list[FakeUpstreamFinding] = Field(default_factory=list)


class TestExtractItemsFromState:
    def test_extracts_from_pydantic_model(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="HIGH",
                    category="logic_error", description="bug",
                ),
            ]
        )
        items = _extract_items_from_state(["code_review"], {"code_review": upstream})
        assert len(items) == 1
        assert items[0]["file"] == "a.py"
        assert items[0]["source"] == "code_review"

    def test_sorts_by_severity(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(file="a.py", line=1, severity="LOW", category="clarity", description="minor"),
                FakeUpstreamFinding(file="b.py", line=2, severity="CRITICAL", category="logic_error", description="crit"),
            ]
        )
        items = _extract_items_from_state(["review"], {"review": upstream})
        assert items[0]["severity"] == "CRITICAL"
        assert items[1]["severity"] == "LOW"

    def test_multiple_upstream_models(self):
        review = FakeUpstreamOutput(findings=[
            FakeUpstreamFinding(file="a.py", line=1, severity="HIGH", category="logic_error", description="bug"),
        ])
        security = FakeUpstreamOutput(findings=[
            FakeUpstreamFinding(file="b.py", line=2, severity="MEDIUM", category="injection", description="sql inj"),
        ])
        items = _extract_items_from_state(
            ["code_review", "security_audit"],
            {"code_review": review, "security_audit": security},
        )
        assert len(items) == 2
        assert items[0]["severity"] == "HIGH"
        assert items[0]["source"] == "code_review"

    def test_skips_none_upstream(self):
        items = _extract_items_from_state(["missing"], {"missing": None})
        assert items == []

    def test_empty_findings_returns_empty(self):
        upstream = FakeUpstreamOutput(findings=[])
        items = _extract_items_from_state(["review"], {"review": upstream})
        assert items == []


class TestFormatFindings:
    def test_no_findings(self):
        result = _format_findings([])
        assert "No findings" in result

    def test_formats_numbered_list(self):
        findings = [
            {"severity": "HIGH", "source": "code_review", "file": "a.py", "line": 10,
             "category": "logic_error", "description": "Off-by-one error"},
            {"severity": "LOW", "source": "docs_review", "file": "b.py", "line": 5,
             "category": "docstring_drift", "description": "Stale docstring"},
        ]
        result = _format_findings(findings)
        assert "1" in result
        assert "2" in result
        assert "HIGH" in result
        assert "LOW" in result
        assert "a.py:10" in result


class TestSelectByInput:
    def _findings(self):
        return [
            {"severity": "CRITICAL", "description": "a"},
            {"severity": "HIGH", "description": "b"},
            {"severity": "MEDIUM", "description": "c"},
            {"severity": "LOW", "description": "d"},
        ]

    def test_all(self):
        assert len(_select_by_input(self._findings(), "all")) == 4

    def test_high_plus(self):
        selected = _select_by_input(self._findings(), "high")
        assert all(f["severity"] in ("CRITICAL", "HIGH") for f in selected)
        assert len(selected) == 2

    def test_medium_plus(self):
        selected = _select_by_input(self._findings(), "medium+")
        assert len(selected) == 3

    def test_by_numbers(self):
        selected = _select_by_input(self._findings(), "1, 3")
        assert len(selected) == 2
        assert selected[0]["description"] == "a"
        assert selected[1]["description"] == "c"

    def test_invalid_input_returns_empty(self):
        assert _select_by_input(self._findings(), "gibberish") == []


class TestResolveOutput:
    def test_resolve_output_validates(self):
        data = {
            "fixed": [{"file": "a.py", "line": 42, "category": "logic_error",
                       "source": "review", "description": "Fixed."}],
            "skipped": [],
        }
        output = ResolveOutput.model_validate(data)
        assert len(output.fixed) == 1


class TestResolveFindingsNode:
    def test_constructs_with_defaults(self):
        node = ResolveFindings()
        assert callable(node)
        assert node.name == "resolve_findings"

    def test_no_findings_returns_immediately(self):
        upstream = FakeUpstreamOutput(findings=[])
        node = ResolveFindings(reads_from=["code_review"])
        result = asyncio.run(node({"working_dir": "/tmp", "code_review": upstream}))
        assert result["last_cost_usd"] == 0.0
        assert isinstance(result["resolve_findings"], ResolveOutput)
        assert result["resolve_findings"].fixed == []

    def test_auto_mode_skips_low_severity(self):
        upstream = FakeUpstreamOutput(
            findings=[FakeUpstreamFinding(file="a.py", line=1, severity="LOW", category="clarity", description="minor")]
        )
        node = ResolveFindings(reads_from=["review"], interactive=False)
        result = asyncio.run(node({"working_dir": "/tmp", "review": upstream}))
        assert result["last_cost_usd"] == 0.0

    def test_interactive_none_skips(self):
        upstream = FakeUpstreamOutput(
            findings=[FakeUpstreamFinding(file="a.py", line=1, severity="HIGH", category="logic_error", description="bug")]
        )

        async def ask_none(_summary):
            return "none"

        node = ResolveFindings(reads_from=["review"], interactive=True, ask_findings=ask_none)
        result = asyncio.run(node({"working_dir": "/tmp", "review": upstream}))
        assert result["last_cost_usd"] == 0.0
