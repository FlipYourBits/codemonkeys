"""Analyzer screen — select targets and kick off analysis."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Checkbox, Static


class AnalyzerScreen(Container):
    DEFAULT_CSS = """
    AnalyzerScreen {
        padding: 1;
    }
    AnalyzerScreen #analyzer-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    AnalyzerScreen .scope-section {
        margin: 0 0 1 0;
        padding: 1;
        background: #1e1f29;
        border: round #44475a;
    }
    AnalyzerScreen .scope-title {
        text-style: bold;
        color: #8be9fd;
        margin: 0 0 1 0;
    }
    AnalyzerScreen #file-list {
        height: auto;
        max-height: 20;
        margin: 1 0;
    }
    AnalyzerScreen #analyze-actions {
        margin: 1 0;
        height: 3;
    }
    """

    class AnalysisRequested(Message):
        def __init__(self, files: list[str]) -> None:
            super().__init__()
            self.files = files

    def compose(self) -> ComposeResult:
        yield Static("Analyze Code", id="analyzer-header")
        with Container(classes="scope-section"):
            yield Static("Select scope", classes="scope-title")
            with Horizontal(id="analyze-actions"):
                yield Button("Changed files", id="btn-changed", classes="-primary")
                yield Button("All files", id="btn-all")
                yield Button("Select files...", id="btn-select")

        yield VerticalScroll(id="file-list")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-changed":
            self._load_changed_files()
        elif event.button.id == "btn-all":
            self._load_all_files()
        elif event.button.id == "btn-run":
            self._run_analysis()

    def _load_changed_files(self) -> None:
        import subprocess

        cwd = self._get_cwd()
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
        self._show_file_list(files)

    def _load_all_files(self) -> None:
        cwd = Path(self._get_cwd())
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(
                part in p.parts
                for part in ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
            )
        ]
        self._show_file_list(sorted(files))

    def _show_file_list(self, files: list[str]) -> None:
        file_list = self.query_one("#file-list", VerticalScroll)
        file_list.remove_children()
        for f in files:
            file_list.mount(Checkbox(f, value=True, id=f"file-{f.replace('/', '__')}"))
        file_list.mount(Button("Run Analysis", id="btn-run", classes="-primary"))

    def _run_analysis(self) -> None:
        selected = []
        for cb in self.query(Checkbox):
            if cb.value:
                label_text = str(cb.label)
                selected.append(label_text)
        self.post_message(self.AnalysisRequested(selected))

    def _get_cwd(self) -> str:
        return str(getattr(self.app, "cwd", Path.cwd()))
