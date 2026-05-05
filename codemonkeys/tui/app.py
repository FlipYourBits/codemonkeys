"""Main Textual application for codemonkeys."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Button, Footer, Header, Static

from codemonkeys.tui.screens.analyzer import AnalyzerScreen
from codemonkeys.tui.screens.dashboard import DashboardScreen
from codemonkeys.tui.screens.queue import QueueScreen


class Sidebar(Container):
    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        background: #1e1f29;
        border-right: solid #44475a;
        padding: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("  [bold #bd93f9]codemonkeys[/]", classes="logo")
        yield Static("")
        yield Button("  Home", id="nav-home", classes="nav-button -active")
        yield Button("  Analyze", id="nav-analyze", classes="nav-button")
        yield Button("  Queue", id="nav-queue", classes="nav-button")
        yield Button("  Dashboard", id="nav-dashboard", classes="nav-button")


class HomeContent(Container):
    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #bd93f9]codemonkeys[/]\n\n"
            "[#6272a4]AI-powered code analysis and implementation workflows[/]",
            classes="welcome-panel",
        )
        with Horizontal():
            with Container(classes="action-card", id="action-review"):
                yield Static("[#8be9fd bold]Run Code Review[/]", classes="action-title")
                yield Static(
                    "[#6272a4]Analyze files for quality and security issues[/]",
                    classes="action-desc",
                )
            with Container(classes="action-card", id="action-implement"):
                yield Static(
                    "[#8be9fd bold]Implement Feature[/]", classes="action-title"
                )
                yield Static(
                    "[#6272a4]Plan and build a feature with TDD[/]",
                    classes="action-desc",
                )


class CodemonkeysApp(App[None]):
    TITLE = "codemonkeys"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home", show=True),
        Binding("a", "go_analyze", "Analyze", show=True),
        Binding("u", "go_queue", "Queue", show=True),
        Binding("d", "go_dashboard", "Dashboard", show=True),
    ]

    def __init__(self, cwd: Path | None = None) -> None:
        super().__init__()
        self.cwd = cwd or Path.cwd()
        self._current_view = "home"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Container(id="main-content"):
                yield HomeContent(id="view-home")
                yield AnalyzerScreen(id="view-analyze")
                yield DashboardScreen(id="view-dashboard")
                yield QueueScreen(id="view-queue")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#view-analyze").display = False
        self.query_one("#view-dashboard").display = False
        self.query_one("#view-queue").display = False

    def action_go_home(self) -> None:
        self._switch_view("home")

    def action_go_analyze(self) -> None:
        self._switch_view("analyze")

    def action_go_queue(self) -> None:
        self._switch_view("queue")

    def action_go_dashboard(self) -> None:
        self._switch_view("dashboard")

    def _switch_view(self, view_id: str) -> None:
        for vid in ("home", "analyze", "dashboard", "queue"):
            widget = self.query_one(f"#view-{vid}")
            widget.display = vid == view_id

        for btn in self.query(".nav-button"):
            btn.remove_class("-active")
        self.query_one(f"#nav-{view_id}", Button).add_class("-active")
        self._current_view = view_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("nav-"):
            view = event.button.id.removeprefix("nav-")
            self._switch_view(view)
        elif event.button.id == "action-review":
            self._switch_view("analyze")
