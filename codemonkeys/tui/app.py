"""Main Textual application for codemonkeys."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Button, Footer, Header, Static


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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Container(id="main-content"):
                yield HomeContent(id="home-content")
        yield Footer()

    def action_go_home(self) -> None:
        self._switch_content("home")

    def action_go_analyze(self) -> None:
        self._switch_content("analyze")

    def action_go_queue(self) -> None:
        self._switch_content("queue")

    def action_go_dashboard(self) -> None:
        self._switch_content("dashboard")

    def _switch_content(self, screen_id: str) -> None:
        for btn in self.query(".nav-button"):
            btn.remove_class("-active")
        nav_btn = self.query_one(f"#nav-{screen_id}", Button)
        nav_btn.add_class("-active")
