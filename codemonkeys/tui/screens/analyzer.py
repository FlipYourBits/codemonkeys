"""Analyzer screen — select targets and kick off analysis."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


class FileItem(Widget, can_focus=True):
    DEFAULT_CSS = """
    FileItem {
        width: 100%;
        height: 1;
        background: transparent;
    }
    FileItem:hover {
        background: $surface-light;
    }
    """

    checked: reactive[bool] = reactive(False)

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self.file_path = file_path

    def render(self) -> str:
        mark = "✓" if self.checked else " "
        return f" [{mark}] {self.file_path}"

    async def _on_click(self, _event: Click) -> None:
        self.checked = not self.checked


class AnalyzerScreen(Container):
    DEFAULT_CSS = """
    AnalyzerScreen {
        padding: 1;
    }
    AnalyzerScreen #analyzer-header {
        text-style: bold;
        color: $accent;
        margin: 0 0 1 0;
    }
    AnalyzerScreen .scope-section {
        margin: 0 0 1 0;
        padding: 1;
        background: $bg-dark;
        border: round $surface-light;
    }
    AnalyzerScreen .scope-title {
        text-style: bold;
        color: $cyan;
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
    AnalyzerScreen #file-actions {
        height: 3;
        margin: 1 0 0 0;
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

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-changed":
            await self._load_changed_files()
        elif event.button.id == "btn-all":
            await self._load_all_files()
        elif event.button.id == "btn-select-all":
            self._toggle_all()
        elif event.button.id == "btn-clear":
            await self._clear_file_list()
        elif event.button.id == "btn-run":
            self._run_analysis()

    async def _load_changed_files(self) -> None:
        import subprocess

        cwd = self._get_cwd()
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
        await self._show_file_list(files)

    async def _load_all_files(self) -> None:
        cwd = Path(self._get_cwd())
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(
                part in p.parts
                for part in ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
            )
        ]
        await self._show_file_list(sorted(files))

    async def _show_file_list(self, files: list[str]) -> None:
        file_list = self.query_one("#file-list", VerticalScroll)
        await file_list.remove_children()
        for f in files:
            await file_list.mount(FileItem(f))
        await file_list.mount(
            Horizontal(
                Button("Select All", id="btn-select-all"),
                Button("Clear", id="btn-clear"),
                Button("Run Analysis", id="btn-run", classes="-primary"),
                id="file-actions",
            )
        )

    async def _clear_file_list(self) -> None:
        file_list = self.query_one("#file-list", VerticalScroll)
        await file_list.remove_children()

    def _toggle_all(self) -> None:
        items = list(self.query(FileItem))
        all_checked = all(item.checked for item in items)
        for item in items:
            item.checked = not all_checked

    def _run_analysis(self) -> None:
        selected = [item.file_path for item in self.query(FileItem) if item.checked]
        if not selected:
            self.app.notify("No files selected", severity="warning")
            return
        self.post_message(self.AnalysisRequested(selected))

    def _get_cwd(self) -> str:
        return str(getattr(self.app, "cwd", Path.cwd()))
