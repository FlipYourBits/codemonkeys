"""Stdout printer — real-time event output for CLI pipelines."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.spinner import Spinner

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    Event,
    EventHandler,
    RateLimitHit,
    RawMessage,
    TextOutput,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.display.formatting import (
    format_tool_call,
    format_tool_result,
    system_message_label,
)


def make_stdout_printer(console: Console | None = None) -> EventHandler:
    """Return an event handler that prints agent activity to the console.

    Shows a live spinner at the bottom while agents are running.
    Event logs scroll above the spinner.
    """
    _console = console or Console(stderr=True)
    _total_cost = 0.0
    _turn = 0
    _last_tool: dict[str, str] = {}
    _current_tool: dict[str, str] = {}
    _running: set[str] = set()
    _live: Live | None = None

    def _spinner_text() -> str:
        parts = []
        for name in sorted(_running):
            tool = _current_tool.get(name, "thinking")
            parts.append(f"{name} [{tool}]")
        return "  ".join(parts)

    def _update_spinner() -> None:
        if _live and _running:
            _live.update(Spinner("dots", text=f" {_spinner_text()}"))

    def _handle(event: Event) -> None:
        nonlocal _total_cost, _turn, _live
        name = event.agent_name

        if isinstance(event, AgentStarted):
            _running.add(name)
            _current_tool[name] = "starting"
            if _live is None:
                _live = Live(
                    Spinner("dots", text=f" {name} starting"),
                    console=_console,
                    refresh_per_second=10,
                )
                _live.start()
            _console.print(f"\n[bold cyan]{name}[/bold cyan] started \\[{event.model}]")
            _update_spinner()

        elif isinstance(event, ThinkingOutput):
            _current_tool[name] = "thinking"
            _update_spinner()

        elif isinstance(event, TextOutput):
            pass

        elif isinstance(event, ToolCall):
            _last_tool[name] = event.tool_name
            detail = format_tool_call(event.tool_name, event.tool_input)
            _current_tool[name] = detail
            _console.print(f"  [dim]{name}[/dim] -> {detail}")
            _update_spinner()

        elif isinstance(event, ToolDenied):
            _console.print(
                f"  [red]{name} DENIED: {event.tool_name}({event.command[:80]})[/red]"
            )

        elif isinstance(event, TokenUpdate):
            _turn += 1
            _total_cost += event.cost_usd
            u = event.usage
            _console.print(
                f"  [dim]{name}[/dim] "
                f"turn {_turn}: [bold]${event.cost_usd:.4f}[/bold] "
                f"({u.input_tokens:,} in + {u.cache_read_tokens:,} cache_read "
                f"+ {u.cache_creation_tokens:,} cache_write / {u.output_tokens:,} out) "
                f"| running: ${_total_cost:.4f}",
                highlight=False,
            )

        elif isinstance(event, RateLimitHit):
            if event.status == "rejected":
                _current_tool[name] = f"rate limited — {event.wait_seconds}s"
                _console.print(
                    f"  [red]{name} rate limited ({event.rate_limit_type}) "
                    f"— waiting {event.wait_seconds}s[/red]"
                )
                _update_spinner()

        elif isinstance(event, RawMessage):
            if event.message_type == "SystemMessage":
                label = system_message_label(event.data)
                _console.print(f"  [dim]{name} << {label}[/dim]")
            elif event.message_type == "UserMessage":
                tool = _last_tool.pop(name, "?")
                hint = format_tool_result(event.data)
                suffix = f": {hint}" if hint else ""
                _console.print(
                    f"  [dim]{name} << {tool} result{suffix}[/dim]"
                )
            elif event.message_type == "ResultMessage":
                data = event.data
                cost_val = data.get("total_cost_usd")
                if cost_val is None:
                    cost_val = data.get("cost", 0) or 0
                _console.print(
                    f"  [dim]{name} << result "
                    f"(turns={data.get('num_turns', '?')}, "
                    f"cost=${cost_val:.4f})[/dim]",
                    highlight=False,
                )

        elif isinstance(event, AgentCompleted):
            _running.discard(name)
            _current_tool.pop(name, None)
            r = event.result
            secs = r.duration_ms / 1000
            duration = f"{secs / 60:.1f}m" if secs >= 60 else f"{secs:.1f}s"
            _console.print(
                f"[bold green]{name}[/bold green] done "
                f"— ${r.cost_usd:.4f} in {duration}"
            )
            if _running:
                _update_spinner()
            elif _live:
                _live.stop()
                _live = None

        elif isinstance(event, AgentError):
            _running.discard(name)
            _current_tool.pop(name, None)
            _console.print(f"[bold red]{name} ERROR: {event.error}[/bold red]")
            if _running:
                _update_spinner()
            elif _live:
                _live.stop()
                _live = None

    return _handle


def fan_out(*handlers: EventHandler) -> EventHandler:
    """Combine multiple event handlers into one."""

    def _handle(event: Event) -> None:
        for h in handlers:
            h(event)

    return _handle
