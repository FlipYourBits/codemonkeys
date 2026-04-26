from __future__ import annotations

from langclaude.findings import (
    dedupe_findings,
    parse_findings,
    passes_threshold,
)


class TestParseFindings:
    def test_parses_fenced_json_report(self):
        text = """
preamble that should be ignored
```json
{
  "findings": [
    {"file": "a.py", "line": 1, "severity": "HIGH", "category": "sqli",
     "description": "x", "recommendation": "y", "confidence": 0.9}
  ]
}
```
trailing junk
"""
        findings = parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["file"] == "a.py"

    def test_parses_bare_json_string(self):
        text = '{"findings": [{"file": "a", "line": 1}]}'
        findings = parse_findings(text)
        assert findings == [{"file": "a", "line": 1}]

    def test_accepts_already_parsed_dict(self):
        report = {"findings": [{"file": "a"}, {"file": "b"}]}
        assert len(parse_findings(report)) == 2

    def test_accepts_single_finding_dict(self):
        f = {"file": "a.py", "line": 3, "severity": "LOW"}
        assert parse_findings(f) == [f]

    def test_accepts_list_of_findings(self):
        items = [{"file": "a"}, {"file": "b"}, "garbage"]
        assert parse_findings(items) == [{"file": "a"}, {"file": "b"}]

    def test_returns_empty_on_garbage(self):
        assert parse_findings("not json at all") == []
        assert parse_findings(None) == []
        assert parse_findings(42) == []
        assert parse_findings({"unrelated": "object"}) == []

    def test_empty_findings_list_ok(self):
        text = '```json\n{"findings": []}\n```'
        assert parse_findings(text) == []


class TestDedupe:
    def test_drops_duplicates_by_file_line_category(self):
        a = {"file": "x.py", "line": 1, "category": "sqli"}
        b = {"file": "x.py", "line": 1, "category": "sqli"}  # dup
        c = {"file": "x.py", "line": 2, "category": "sqli"}  # different line
        d = {"file": "x.py", "line": 1, "category": "xss"}   # different cat
        out = dedupe_findings([a, b, c, d])
        assert len(out) == 3

    def test_first_wins(self):
        a = {"file": "x", "line": 1, "category": "c", "source": "first"}
        b = {"file": "x", "line": 1, "category": "c", "source": "second"}
        assert dedupe_findings([a, b])[0]["source"] == "first"


class TestPassesThreshold:
    def test_high_passes_default_high_gate(self):
        f = {"severity": "HIGH", "confidence": 0.9}
        assert passes_threshold(f, severity_threshold="HIGH")

    def test_medium_blocked_by_high_gate(self):
        f = {"severity": "MEDIUM", "confidence": 0.95}
        assert not passes_threshold(f, severity_threshold="HIGH")

    def test_low_confidence_blocked(self):
        f = {"severity": "HIGH", "confidence": 0.5}
        assert not passes_threshold(
            f, severity_threshold="HIGH", confidence_threshold=0.8
        )

    def test_missing_fields_default_to_block(self):
        assert not passes_threshold({}, severity_threshold="HIGH")

    def test_lowercase_severity_handled(self):
        f = {"severity": "high", "confidence": 0.9}
        assert passes_threshold(f, severity_threshold="HIGH")
