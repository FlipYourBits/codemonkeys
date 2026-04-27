from __future__ import annotations

import sys
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text


_STATUS_PENDING = Text("·", style="dim")
_STATUS_DONE = Text("✓", style="bold green")
_STATUS_RUNNING = Text("⠸", style="bold cyan")
_STATUS_SKIP = Text("—", style="dim")

_MAX_OUTPUT_LINES = 5


class Display:
    def __init__(
        self,
        *,
        steps: list[str],
        title: str,
        live: bool = True,
    ) -> None:
        self.title = title
        self._steps = list(steps)
        self._console = Console(stderr=True)
        self._stdout_console = Console()
        self._use_live = live and sys.stderr.isatty()

        self._statuses: dict[str, Text] = {s: _STATUS_PENDING.copy() for s in steps}
        self._timings: dict[str, str] = {s: "—" for s in steps}
        self._output_lines: list[str] = []
        self._active_node: str | None = None
        self._live: Live | None = None

        if self._use_live:
            self._live = Live(
                self._build_renderable(),
                console=self._console,
                refresh_per_second=8,
            )
            self._live.start()

    def _build_table(self) -> Table:
        table = Table(
            title=self.title,
            title_style="bold",
            show_header=False,
            box=None,
            padding=(0, 1),
            expand=False,
        )
        table.add_column("name", style="bold")
        table.add_column("status", width=3, justify="center")
        table.add_column("time", style="dim", justify="right")
        for step in self._steps:
            status = self._statuses.get(step, _STATUS_PENDING)
            timing = self._timings.get(step, "—")
            name_style = "bold" if status == _STATUS_RUNNING else ("dim" if status == _STATUS_PENDING else "")
            table.add_row(
                Text(step, style=name_style),
                status,
                Text(timing, style="dim"),
            )
        return table

    def _build_output_panel(self) -> Text | None:
        if not self._output_lines:
            return None
        lines = self._output_lines[-_MAX_OUTPUT_LINES:]
        content = "\n".join(lines)
        return Text(content, style="dim")

    def _build_renderable(self) -> Group:
        parts: list[Any] = [self._build_table()]
        panel = self._build_output_panel()
        if panel is not None:
            parts.append(Text(""))
            parts.append(panel)
        return Group(*parts)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._build_renderable())

    def node_start(self, name: str) -> None:
        self._active_node = name
        self._output_lines.clear()
        self._statuses[name] = _STATUS_RUNNING.copy()
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"● {name}...", end="", highlight=False)

    def node_done(self, name: str, elapsed: float, cost: float = 0.0) -> None:
        self._statuses[name] = _STATUS_DONE.copy()
        cost_str = f", ${cost:.4f}" if cost > 0 else ""
        self._timings[name] = f"{elapsed:.1f}s{cost_str}"
        self._output_lines.clear()
        self._active_node = None
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f" done ({elapsed:.1f}s{cost_str})", highlight=False)

    def node_skip(self, name: str) -> None:
        self._statuses[name] = _STATUS_SKIP.copy()
        self._timings[name] = "—"
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"  {name} skipped", highlight=False)

    def node_output(self, name: str, line: str) -> None:
        self._output_lines.append(line)
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"  [{name}] {line}", highlight=False)

    def warn(self, text: str) -> None:
        if self._use_live and self._live is not None:
            self._live.console.print(f"[yellow bold]⚠ {text}[/]")
        else:
            self._console.print(f"[yellow bold]⚠ {text}[/]")

    def prompt(self, text: str, content: str | None = None) -> str:
        if self._live is not None:
            self._live.stop()
        try:
            if content is not None:
                self._console.rule()
                self._console.print(content, highlight=False)
                self._console.rule()
            return self._console.input(f"  {text} ")
        finally:
            if self._live is not None:
                self._live.start()

    def print_results(self, node_costs: dict[str, float]) -> None:
        self.stop()
        table = Table(title="Results", show_header=True, expand=False)
        table.add_column("Node", style="bold")
        table.add_column("Cost", justify="right")
        total = 0.0
        for name, cost in node_costs.items():
            table.add_row(name, f"${cost:.4f}")
            total += cost
        table.add_section()
        table.add_row(Text("Total", style="bold"), Text(f"${total:.4f}", style="bold green"))
        self._stdout_console.print(table)

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
