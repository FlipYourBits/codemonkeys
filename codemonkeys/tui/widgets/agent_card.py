"""Live agent status card widget."""

from __future__ import annotations

from enum import Enum

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label


class AgentStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AgentCard(Widget):
    DEFAULT_CSS = """
    AgentCard {
        height: 3;
        padding: 0 1;
        background: #282a36;
        border: round #44475a;
        layout: horizontal;
    }
    AgentCard.-running { border: round #f1fa8c; }
    AgentCard.-done { border: round #50fa7b; }
    AgentCard.-failed { border: round #ff5555; }
    AgentCard .card-name { width: 1fr; color: #8be9fd; text-style: bold; }
    AgentCard .card-tool { width: 1fr; color: #6272a4; }
    AgentCard .card-status { width: 10; }
    AgentCard .card-tokens { width: 14; text-align: right; color: #6272a4; }
    """

    status: reactive[AgentStatus] = reactive(AgentStatus.RUNNING)
    tokens: reactive[int] = reactive(0)
    tool_calls: reactive[int] = reactive(0)
    current_tool: reactive[str] = reactive("")

    def __init__(self, agent_name: str, task_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.task_id = task_id

    def compose(self) -> ComposeResult:
        yield Label(self.agent_name, classes="card-name")
        yield Label("", classes="card-tool", id="tool-label")
        yield Label("running", classes="card-status", id="status-label")
        yield Label("0 tok", classes="card-tokens", id="tokens-label")

    def update_progress(
        self, tokens: int = 0, tool_calls: int = 0, current_tool: str = ""
    ) -> None:
        self.tokens = tokens
        self.tool_calls = tool_calls
        self.current_tool = current_tool

    def mark_done(self, tokens: int = 0) -> None:
        self.tokens = tokens
        self.status = AgentStatus.DONE

    def mark_failed(self) -> None:
        self.status = AgentStatus.FAILED

    def watch_status(self, value: AgentStatus) -> None:
        self.remove_class("-running", "-done", "-failed")
        self.add_class(f"-{value.value}")
        try:
            self.query_one("#status-label", Label).update(value.value)
        except Exception:
            pass

    def watch_tokens(self, value: int) -> None:
        try:
            self.query_one("#tokens-label", Label).update(f"{value:,} tok")
        except Exception:
            pass

    def watch_current_tool(self, value: str) -> None:
        try:
            self.query_one("#tool-label", Label).update(value[:40])
        except Exception:
            pass
