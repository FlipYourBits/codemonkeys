"""Queue screen — browse artifacts, select findings, dispatch fixers."""

from __future__ import annotations


from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Static

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.tui.widgets.finding_view import FindingView


class QueueScreen(Container):
    DEFAULT_CSS = """
    QueueScreen {
        padding: 1;
    }
    QueueScreen #queue-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    QueueScreen .run-item {
        height: 3;
        padding: 0 1;
        background: #1e1f29;
        border: round #44475a;
        margin: 0 0 0 0;
    }
    QueueScreen .run-item:hover {
        border: round #bd93f9;
    }
    QueueScreen .file-summary {
        height: 3;
        padding: 0 1;
        background: #282a36;
        border: round #44475a;
        margin: 0 0 0 0;
    }
    QueueScreen .file-summary:hover {
        border: round #8be9fd;
    }
    QueueScreen #findings-scroll {
        height: 1fr;
    }
    QueueScreen #queue-actions {
        height: 3;
        margin: 1 0 0 0;
    }
    """

    class FixRequested(Message):
        def __init__(self, fix_requests: list[FixRequest]) -> None:
            super().__init__()
            self.fix_requests = fix_requests

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._current_findings: list[FileFindings] = []

    def compose(self) -> ComposeResult:
        yield Static("Review Queue", id="queue-header")
        yield VerticalScroll(id="findings-scroll")
        with Horizontal(id="queue-actions"):
            yield Button("Fix Selected", id="btn-fix-selected", classes="-primary")
            yield Button("Fix All High", id="btn-fix-high", classes="-danger")
            yield Button("Back", id="btn-back")

    def load_findings(self, findings_list: list[FileFindings]) -> None:
        self._current_findings = findings_list
        scroll = self.query_one("#findings-scroll", VerticalScroll)
        scroll.remove_children()

        for file_findings in findings_list:
            if not file_findings.findings:
                continue
            high = sum(1 for f in file_findings.findings if f.severity == "high")
            med = sum(1 for f in file_findings.findings if f.severity == "medium")
            low = sum(1 for f in file_findings.findings if f.severity == "low")

            counts = []
            if high:
                counts.append(f"[#ff5555]{high} high[/]")
            if med:
                counts.append(f"[#ffb86c]{med} med[/]")
            if low:
                counts.append(f"[#8be9fd]{low} low[/]")

            scroll.mount(
                Static(
                    f"[bold #8be9fd]{file_findings.file}[/]  "
                    f"{len(file_findings.findings)} findings ({', '.join(counts)})",
                    classes="file-summary",
                )
            )
            for finding in file_findings.findings:
                scroll.mount(FindingView(finding=finding))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-fix-selected":
            self._fix_selected()
        elif event.button.id == "btn-fix-high":
            self._fix_high_severity()

    def _fix_selected(self) -> None:
        fix_requests = self._collect_selected_findings()
        if fix_requests:
            self.post_message(self.FixRequested(fix_requests))

    def _fix_high_severity(self) -> None:
        requests: dict[str, list[Finding]] = {}
        for file_findings in self._current_findings:
            for finding in file_findings.findings:
                if finding.severity == "high":
                    requests.setdefault(finding.file, []).append(finding)
        fix_requests = [
            FixRequest(file=f, findings=findings) for f, findings in requests.items()
        ]
        if fix_requests:
            self.post_message(self.FixRequested(fix_requests))

    def _collect_selected_findings(self) -> list[FixRequest]:
        requests: dict[str, list[Finding]] = {}
        for view in self.query(FindingView):
            if view.selected:
                requests.setdefault(view.finding.file, []).append(view.finding)
        return [
            FixRequest(file=f, findings=findings) for f, findings in requests.items()
        ]
