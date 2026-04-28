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

_MAX_OUTPUT_LINES = 8


class Display:
    """Rich-based pipeline progress display.

    Shows a step table with status indicators.  Uses a ``Live`` widget on
    TTY stderr; falls back to plain prints otherwise.

    Args:
        steps: Ordered node names shown in the progress table.
        title: Table title.
        live: Enable live-updating display (ignored when stderr is not a TTY).
    """

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
        self._running: set[str] = set()
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
            name_style = (
                "bold"
                if status == _STATUS_RUNNING
                else ("dim" if status == _STATUS_PENDING else "")
            )
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
        """Mark *name* as running and refresh the display."""
        if not self._running:
            self._output_lines.clear()
        self._running.add(name)
        self._statuses[name] = _STATUS_RUNNING.copy()
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"● {name}...", end="", highlight=False)

    def node_done(self, name: str, elapsed: float, cost: float = 0.0) -> None:
        """Mark *name* as complete with elapsed time and optional cost."""
        self._statuses[name] = _STATUS_DONE.copy()
        cost_str = f", ${cost:.4f}" if cost > 0 else ""
        self._timings[name] = f"{elapsed:.1f}s{cost_str}"
        self._running.discard(name)
        if not self._running:
            self._output_lines.clear()
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f" done ({elapsed:.1f}s{cost_str})", highlight=False)

    def node_skip(self, name: str) -> None:
        """Mark *name* as skipped."""
        self._statuses[name] = _STATUS_SKIP.copy()
        self._timings[name] = "—"
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"  {name} skipped", highlight=False)

    def node_output(self, name: str, line: str) -> None:
        """Append a streaming output line for the given node."""
        self._output_lines.append(f"[{name}] {line}")
        if self._use_live:
            self._refresh()
        else:
            self._console.print(f"  [{name}] {line}", highlight=False)

    def warn(self, text: str) -> None:
        """Print a yellow warning, bypassing the live widget if active."""
        if self._use_live and self._live is not None:
            self._live.console.print(f"[yellow bold]⚠ {text}[/]")
        else:
            self._console.print(f"[yellow bold]⚠ {text}[/]")

    def prompt(self, text: str, content: str | None = None) -> str:
        """Pause live display, prompt the user, and resume."""
        if self._live is not None:
            self._live.stop()
        try:
            if content is not None:
                self._console.print()
                self._console.print(content, highlight=False)
                self._console.print()
            return self._console.input(f"  {text} ")
        finally:
            if self._live is not None:
                self._live.start()

    def print_results(
        self,
        node_costs: dict[str, float],
        node_outputs: dict[str, str] | None = None,
    ) -> None:
        """Stop live display and print a per-node cost summary table."""
        self.stop()
        table = Table(title=self.title, show_header=True, expand=False)
        table.add_column("Node", style="bold")
        table.add_column("Cost", justify="right")
        total = 0.0
        for name, cost in node_costs.items():
            table.add_row(name, f"${cost:.4f}")
            total += cost
        table.add_section()
        table.add_row(
            Text("Total", style="bold"), Text(f"${total:.4f}", style="bold green")
        )
        self._stdout_console.print(table)

        if node_outputs:
            resolve_output = node_outputs.get("resolve_findings", "")
            if resolve_output:
                self._stdout_console.print()
                self._stdout_console.print(
                    Text("Resolve findings", style="bold underline")
                )
                try:
                    import json

                    data = json.loads(resolve_output)
                    fixed = data.get("fixed", [])
                    skipped = data.get("skipped", [])
                    if fixed:
                        self._stdout_console.print(
                            Text(f"\n  Fixed ({len(fixed)}):", style="bold green")
                        )
                        for f in fixed:
                            file = f.get("file", "?")
                            line = f.get("line", "?")
                            desc = f.get("description", "")
                            self._stdout_console.print(
                                f"    {file}:{line} — {desc}", highlight=False
                            )
                    if skipped:
                        self._stdout_console.print(
                            Text(f"\n  Skipped ({len(skipped)}):", style="bold yellow")
                        )
                        for s in skipped:
                            file = s.get("file", "?")
                            line = s.get("line", "?")
                            reason = s.get("reason", "")
                            self._stdout_console.print(
                                f"    {file}:{line} — {reason}", highlight=False
                            )
                    if not fixed and not skipped:
                        self._stdout_console.print(
                            "  No findings to resolve.", highlight=False
                        )
                except (json.JSONDecodeError, TypeError):
                    self._stdout_console.print(resolve_output, highlight=False)

    def stop(self) -> None:
        """Stop and discard the live widget (idempotent)."""
        if self._live is not None:
            self._live.stop()
            self._live = None


def default_prompt(text: str, content: str | None = None) -> str:
    if content is not None:
        print(file=sys.stderr)
        print(content, file=sys.stderr)
        print(file=sys.stderr)
    return input(f"\n{text} ")
