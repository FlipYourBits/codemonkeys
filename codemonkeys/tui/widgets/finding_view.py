"""Rendered finding with severity badge, description, and selection toggle."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Checkbox, Label, Static

from codemonkeys.artifacts.schemas.findings import Finding

_SEVERITY_STYLES = {
    "high": "bold #ff5555",
    "medium": "#ffb86c",
    "low": "#8be9fd",
    "info": "#6272a4",
}


class FindingView(Widget):
    DEFAULT_CSS = """
    FindingView {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        background: #1e1f29;
        border: round #44475a;
    }
    FindingView.-selected {
        border: round #bd93f9;
    }
    FindingView .finding-header {
        height: 1;
    }
    FindingView .finding-badge {
        width: 8;
        text-style: bold;
    }
    FindingView .finding-title {
        width: 1fr;
        text-style: bold;
    }
    FindingView .finding-location {
        width: 20;
        text-align: right;
        color: #6272a4;
    }
    FindingView .finding-body {
        margin: 1 0 0 2;
        color: #f8f8f2;
    }
    FindingView .finding-suggestion {
        margin: 1 0 0 2;
        color: #50fa7b;
    }
    """

    selected: reactive[bool] = reactive(True)

    def __init__(self, finding: Finding, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.finding = finding

    def compose(self) -> ComposeResult:
        style = _SEVERITY_STYLES.get(self.finding.severity, "#f8f8f2")
        location = (
            f"{self.finding.file}:{self.finding.line}"
            if self.finding.line
            else self.finding.file
        )

        with Horizontal(classes="finding-header"):
            yield Checkbox("", value=True, id="finding-toggle")
            yield Label(
                f"[{style}]{self.finding.severity.upper()}[/]", classes="finding-badge"
            )
            yield Label(self.finding.title, classes="finding-title")
            yield Label(location, classes="finding-location")

        yield Static(self.finding.description, classes="finding-body")
        if self.finding.suggestion:
            yield Static(
                f"Fix: {self.finding.suggestion}", classes="finding-suggestion"
            )

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.selected = event.value
        if self.selected:
            self.add_class("-selected")
        else:
            self.remove_class("-selected")
