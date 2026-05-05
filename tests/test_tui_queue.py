from __future__ import annotations


from codemonkeys.artifacts.schemas.findings import Finding
from codemonkeys.tui.widgets.finding_view import FindingView


class TestFindingView:
    def test_instantiates_with_finding(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection via f-string",
            description="User input interpolated into SQL query.",
            suggestion="Use parameterized query.",
        )
        view = FindingView(finding=finding)
        assert view.finding.severity == "high"
        assert view.selected is True
