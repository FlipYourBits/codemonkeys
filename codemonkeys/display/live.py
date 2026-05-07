"""Rich Live display — real-time agent status cards."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    RateLimitHit,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.types import TokenUsage


@dataclass
class AgentState:
    """Mutable state for one running agent."""

    name: str
    model: str
    current_tool: str = ""
    tool_calls: int = 0
    denied_calls: int = 0
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0))
    cost_usd: float = 0.0
    completed: bool = False
    error: str | None = None


class LiveDisplay:
    """Rich Live display that renders per-agent status cards.

    Usage:
        display = LiveDisplay()
        display.start()
        result = await run_agent(agent, prompt, on_event=display.handle)
        display.stop()
    """

    def __init__(self) -> None:
        self.agents: dict[str, AgentState] = {}
        self._console = Console()
        self._live: Live | None = None

    def start(self) -> None:
        self._live = Live(self._render(), console=self._console, refresh_per_second=8)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def handle(self, event: Event) -> None:
        if isinstance(event, AgentStarted):
            self.agents[event.agent_name] = AgentState(
                name=event.agent_name, model=event.model
            )
        elif isinstance(event, ToolCall):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.current_tool = event.tool_name
                state.tool_calls += 1
        elif isinstance(event, ToolDenied):
            if event.agent_name in self.agents:
                self.agents[event.agent_name].denied_calls += 1
        elif isinstance(event, TokenUpdate):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.usage = event.usage
                state.cost_usd = event.cost_usd
        elif isinstance(event, AgentCompleted):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.completed = True
                state.cost_usd = event.result.cost_usd
                state.usage = event.result.usage
        elif isinstance(event, RateLimitHit):
            if event.agent_name in self.agents:
                self.agents[
                    event.agent_name
                ].current_tool = f"rate limited — retrying in {event.wait_seconds}s"
        elif isinstance(event, AgentError):
            if event.agent_name in self.agents:
                state = self.agents[event.agent_name]
                state.error = event.error
                state.completed = True

        if self._live:
            self._live.update(self._render())

    def _render(self) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column()

        total_cost = 0.0
        running = 0

        for state in self.agents.values():
            total_cost += state.cost_usd
            if state.completed:
                style = "red" if state.error else "green"
                status = f"[{style}]done[/{style}]"
                if state.error:
                    status = f"[red]error: {state.error[:60]}[/red]"
                line = Text.from_markup(
                    f"  {state.name} [{state.model}] — ${state.cost_usd:.4f} — {status}"
                )
                table.add_row(line)
            else:
                running += 1
                tokens_in = f"{state.usage.input_tokens:,}"
                tokens_out = f"{state.usage.output_tokens:,}"
                tool_line = state.current_tool or "..."
                if state.denied_calls:
                    tool_line += f" [red]({state.denied_calls} denied)[/red]"
                content = Text.from_markup(
                    f"  Tool: {tool_line}\n"
                    f"  Tokens: {tokens_in} in / {tokens_out} out  "
                    f"Cost: ${state.cost_usd:.4f}"
                )
                panel = Panel(
                    content,
                    title=f"{state.name} [{state.model}]",
                    title_align="left",
                    border_style="blue",
                )
                table.add_row(panel)

        footer = Text.from_markup(
            f"\n  Totals: ${total_cost:.4f} | {running} agent(s) running"
        )
        table.add_row(footer)
        return table
