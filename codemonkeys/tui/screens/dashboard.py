"""Full-screen agent monitoring dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from codemonkeys.tui.widgets.agent_card import AgentCard


class DashboardScreen(Container):
    DEFAULT_CSS = """
    DashboardScreen {
        padding: 1;
    }
    DashboardScreen #dashboard-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    DashboardScreen #agent-list {
        height: 1fr;
    }
    DashboardScreen #no-agents {
        color: #6272a4;
        text-align: center;
        margin: 4 0;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cards: dict[str, AgentCard] = {}

    def compose(self) -> ComposeResult:
        yield Static("Agent Dashboard", id="dashboard-header")
        yield VerticalScroll(
            Static("No agents running", id="no-agents"),
            id="agent-list",
        )

    def add_agent(self, agent_name: str, task_id: str) -> None:
        card = AgentCard(agent_name=agent_name, task_id=task_id)
        self._cards[task_id] = card
        agent_list = self.query_one("#agent-list", VerticalScroll)
        no_agents = self.query("#no-agents")
        if no_agents:
            no_agents.first().remove()
        agent_list.mount(card)

    def update_agent(
        self, task_id: str, tokens: int = 0, tool_calls: int = 0, current_tool: str = ""
    ) -> None:
        if task_id in self._cards:
            self._cards[task_id].update_progress(tokens, tool_calls, current_tool)

    def complete_agent(self, task_id: str, tokens: int = 0) -> None:
        if task_id in self._cards:
            self._cards[task_id].mark_done(tokens)
