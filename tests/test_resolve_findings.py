from __future__ import annotations

import asyncio
import json

from agentpipe.nodes.resolve_findings import (
    _extract_findings,
    _format_findings,
    _select_by_input,
    resolve_findings_node,
)


class TestExtractFindings:
    def test_extracts_from_markdown_sections(self):
        prior = (
            "## Prior results\n\n"
            "### code_review\n"
            '```json\n{"findings": [{"severity": "HIGH", "file": "a.py", '
            '"line": 1, "category": "logic_error", "description": "bug"}]}\n```\n\n'
            "### security_audit\n"
            '```json\n{"findings": []}\n```\n'
        )
        findings = _extract_findings(prior)
        assert len(findings) == 1
        assert findings[0]["source"] == "code_review"
        assert findings[0]["severity"] == "HIGH"

    def test_sorts_by_severity(self):
        prior = (
            "### node_a\n"
            '```json\n{"findings": [\n'
            '  {"severity": "LOW", "description": "low"},\n'
            '  {"severity": "CRITICAL", "description": "crit"}\n'
            "]}\n```\n"
        )
        findings = _extract_findings(prior)
        assert findings[0]["severity"] == "CRITICAL"
        assert findings[1]["severity"] == "LOW"

    def test_no_json_returns_empty(self):
        assert _extract_findings("### node\nno json here\n") == []

    def test_malformed_json_skipped(self):
        prior = "### node\n```json\n{invalid json}\n```\n"
        assert _extract_findings(prior) == []

    def test_empty_string(self):
        assert _extract_findings("") == []


class TestFormatFindings:
    def test_no_findings(self):
        result = _format_findings([])
        assert "No findings" in result

    def test_formats_numbered_list(self):
        findings = [
            {
                "severity": "HIGH",
                "source": "code_review",
                "file": "a.py",
                "line": 10,
                "category": "logic_error",
                "description": "Off-by-one error",
            },
            {
                "severity": "LOW",
                "source": "docs_review",
                "file": "b.py",
                "line": 5,
                "category": "docstring_drift",
                "description": "Stale docstring",
            },
        ]
        result = _format_findings(findings)
        assert "1." in result
        assert "2." in result
        assert "[HIGH]" in result
        assert "[LOW]" in result
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


class TestResolveFindingsNode:
    def test_constructs_with_defaults(self):
        node = resolve_findings_node()
        assert callable(node)
        assert node.__name__ == "resolve_findings"

    def test_no_findings_returns_immediately(self):
        node = resolve_findings_node()
        result = asyncio.run(node({"working_dir": "/tmp", "_prior_results": ""}))
        assert result["last_cost_usd"] == 0.0
        data = json.loads(result["resolve_findings"])
        assert data["fixed"] == []

    def test_auto_mode_skips_low_severity(self):
        prior = (
            "### code_review\n"
            '```json\n{"findings": [{"severity": "LOW", "file": "a.py", '
            '"line": 1, "category": "clarity", "description": "minor"}]}\n```\n'
        )
        node = resolve_findings_node(interactive=False)
        result = asyncio.run(node({"working_dir": "/tmp", "_prior_results": prior}))
        assert result["last_cost_usd"] == 0.0

    def test_interactive_none_skips(self):
        prior = (
            "### code_review\n"
            '```json\n{"findings": [{"severity": "HIGH", "file": "a.py", '
            '"line": 1, "category": "logic_error", "description": "bug"}]}\n```\n'
        )

        async def ask_none(_summary):
            return "none"

        node = resolve_findings_node(interactive=True, ask_findings=ask_none)
        result = asyncio.run(node({"working_dir": "/tmp", "_prior_results": prior}))
        assert result["last_cost_usd"] == 0.0
