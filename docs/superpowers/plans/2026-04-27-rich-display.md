# Rich Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all plain `print()` output with a `rich`-powered live-updating pipeline table and collapsing output panel.

**Architecture:** A single `Display` class in `langclaude/display.py` owns all terminal output via `rich.console.Console` and `rich.live.Live`. Pipeline creates and owns the Display instance, wiring it into tracking wraps, node printers, budget warnings, and interactive callbacks. Non-TTY environments fall back to styled sequential output without Live.

**Tech Stack:** `rich>=13.0,<14` (Console, Live, Table, Text, Spinner, Group)

---

## File Structure

| File | Role |
|------|------|
| `langclaude/display.py` | New. `Display` class — all rich rendering, Live management, prompt pause/resume. |
| `tests/test_display.py` | New. Tests for Display (non-TTY / `live=False` mode). |
| `pyproject.toml` | Add `rich` dependency. |
| `langclaude/pipeline.py` | Create Display in `run()`, wire into tracking wraps. |
| `langclaude/nodes/base.py` | `_make_printer` accepts optional Display, routes output through it. |
| `langclaude/budget.py` | `default_on_warn` routes through Display. |
| `langclaude/nodes/python_plan_feature.py` | `ask_plan_feedback_via_stdin` uses `prompt_fn`. |
| `langclaude/nodes/python_implement_feature.py` | `ask_impl_feedback_via_stdin` uses `prompt_fn`. |
| `langclaude/nodes/git_commit.py` | `ask_push_via_stdin` uses `prompt_fn`. |
| `langclaude/permissions.py` | `ask_via_stdin` uses `prompt_fn`. |
| `langclaude/graphs/python_quality_gate.py` | `main()` uses `Display.print_results()`. |
| `langclaude/graphs/python_new_feature.py` | `main()` uses `Display.print_results()`. |
| `langclaude/__init__.py` | Export `Display`. |

---

### Task 1: Add `rich` dependency

**Files:**
- Modify: `pyproject.toml:28` (dependencies list)

- [ ] **Step 1: Add rich to dependencies**

In `pyproject.toml`, add `"rich>=13.0,<14"` to the `dependencies` list:

```toml
dependencies = [
    "claude-agent-sdk>=0.1.0,<0.2",
    "langgraph>=1.0.10,<2",
    "rich>=13.0,<14",
]
```

- [ ] **Step 2: Install and verify**

Run: `.venv/bin/pip install -e .`
Expected: rich installs successfully.

Run: `.venv/bin/python -c "import rich; print(rich.__version__)"`
Expected: prints a version like `13.x.x`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add rich dependency for terminal display"
```

---

### Task 2: Display class — core rendering (non-TTY path)

**Files:**
- Create: `langclaude/display.py`
- Create: `tests/test_display.py`

- [ ] **Step 1: Write failing tests for non-TTY Display**

Create `tests/test_display.py`:

```python
from __future__ import annotations

import pytest

from langclaude.display import Display


class TestDisplayNonLive:
    """Test Display with live=False (non-TTY / CI fallback)."""

    def test_construct_with_steps(self):
        d = Display(steps=["lint", "test"], title="Test", live=False)
        assert d.title == "Test"

    def test_node_start_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        err = capsys.readouterr().err
        assert "lint" in err

    def test_node_done_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_done("lint", elapsed=1.5, cost=0.0)
        err = capsys.readouterr().err
        assert "done" in err
        assert "1.5" in err

    def test_node_done_with_cost(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_done("lint", elapsed=2.0, cost=0.0312)
        err = capsys.readouterr().err
        assert "$0.0312" in err

    def test_node_output_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_output("lint", "→ Read(foo.py)")
        err = capsys.readouterr().err
        assert "Read(foo.py)" in err

    def test_node_skip_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_skip("lint")
        err = capsys.readouterr().err
        assert "lint" in err

    def test_warn_prints_yellow(self, capsys):
        d = Display(steps=[], title="T", live=False)
        d.warn("budget exceeded")
        err = capsys.readouterr().err
        assert "budget exceeded" in err

    def test_prompt_returns_input(self, monkeypatch):
        d = Display(steps=[], title="T", live=False)
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        result = d.prompt("Continue?")
        assert result == "yes"

    def test_prompt_with_content(self, capsys, monkeypatch):
        d = Display(steps=[], title="T", live=False)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        d.prompt("Approve?", content="Here is the plan")
        err = capsys.readouterr().err
        assert "plan" in err

    def test_print_results_table(self, capsys):
        d = Display(steps=["a", "b"], title="T", live=False)
        d.print_results({"a": 0.05, "b": 0.10})
        out = capsys.readouterr().out
        assert "a" in out
        assert "b" in out
        assert "total" in out.lower() or "Total" in out

    def test_stop_is_safe_when_not_live(self):
        d = Display(steps=[], title="T", live=False)
        d.stop()  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_display.py -x -q --no-header`
Expected: `ModuleNotFoundError: No module named 'langclaude.display'`

- [ ] **Step 3: Implement Display class**

Create `langclaude/display.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_display.py -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add langclaude/display.py tests/test_display.py
git commit -m "feat: add Display class with rich live table and non-TTY fallback"
```

---

### Task 3: Display class — Live mode tests

**Files:**
- Modify: `tests/test_display.py`

- [ ] **Step 1: Write tests for Live mode behavior**

Append to `tests/test_display.py`:

```python
class TestDisplayLive:
    """Test Display with live=True but mocked stderr.isatty."""

    def test_live_starts_when_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        assert d._live is not None
        d.stop()

    def test_live_skipped_when_not_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: False)
        d = Display(steps=["a"], title="T", live=True)
        assert d._live is None

    def test_node_lifecycle(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a", "b"], title="T", live=True)
        d.node_start("a")
        d.node_output("a", "→ Read(x.py)")
        d.node_done("a", elapsed=1.0, cost=0.01)
        d.node_start("b")
        d.node_done("b", elapsed=0.5)
        d.stop()
        assert d._live is None

    def test_prompt_pauses_live(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        d.node_start("a")

        monkeypatch.setattr("builtins.input", lambda _: "yes")
        result = d.prompt("Continue?")
        assert result == "yes"
        # Live should have restarted
        assert d._live is not None
        d.stop()

    def test_stop_idempotent(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        d.stop()
        d.stop()  # should not raise
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_display.py -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_display.py
git commit -m "test: add Live mode tests for Display"
```

---

### Task 4: Wire Display into Pipeline

**Files:**
- Modify: `langclaude/pipeline.py:1-270`

The Pipeline currently prints status in `_make_tracking_wrap` using `print()`. Replace this with Display calls. The Display is created in `run()` and threaded through via `self._display`.

- [ ] **Step 1: Write failing test**

Add to `tests/test_pipeline.py` inside `TestStatusLine`:

```python
    def test_normal_verbosity_uses_display(self):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.normal,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        assert p._display is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py::TestStatusLine::test_normal_verbosity_uses_display -x -q --no-header`
Expected: `AttributeError: 'Pipeline' object has no attribute '_display'`

- [ ] **Step 3: Implement Pipeline integration**

Modify `langclaude/pipeline.py`. Add import at the top:

```python
from langclaude.display import Display
```

Add `self._display: Display | None = None` in `__init__` after `self.extra_state`.

Replace `_make_tracking_wrap` to use Display. The async wrapper becomes:

```python
    def _make_tracking_wrap(self, graph_name: str, node: Any) -> Any:
        if Pipeline._is_async(node):

            async def _wrapper(state):
                state = self._inject_prior_results(state, graph_name)

                if self._display is not None:
                    self._display.node_start(graph_name)
                    t0 = time.time()

                result = await node(state)

                if not isinstance(result, dict):
                    if self._display is not None:
                        self._display.node_done(graph_name, elapsed=time.time() - t0)
                    return result

                cost = result.pop("last_cost_usd", 0.0)

                if self._display is not None:
                    elapsed = time.time() - t0
                    self._display.node_done(graph_name, elapsed=elapsed, cost=cost)

                node_costs = {**state.get("node_costs", {}), graph_name: cost}
                total_cost = state.get("total_cost_usd", 0.0) + cost
                node_outputs = {**state.get("node_outputs", {})}
                if graph_name in result:
                    node_outputs[graph_name] = result[graph_name]
                return {
                    **state,
                    **result,
                    "node_costs": node_costs,
                    "total_cost_usd": total_cost,
                    "node_outputs": node_outputs,
                }

            return _wrapper

        def _wrapper(state):
            state = self._inject_prior_results(state, graph_name)

            if self._display is not None:
                self._display.node_start(graph_name)
                t0 = time.time()

            result = node(state)

            if not isinstance(result, dict):
                if self._display is not None:
                    self._display.node_done(graph_name, elapsed=time.time() - t0)
                return result

            cost = result.pop("last_cost_usd", 0.0)

            if self._display is not None:
                elapsed = time.time() - t0
                self._display.node_done(graph_name, elapsed=elapsed, cost=cost)

            node_costs = {**state.get("node_costs", {}), graph_name: cost}
            total_cost = state.get("total_cost_usd", 0.0) + cost
            node_outputs = {**state.get("node_outputs", {})}
            if graph_name in result:
                node_outputs[graph_name] = result[graph_name]
            return {
                **state,
                **result,
                "node_costs": node_costs,
                "total_cost_usd": total_cost,
                "node_outputs": node_outputs,
            }

        return _wrapper
```

Modify `run()` to create and tear down the Display:

```python
    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            ordered = self._flatten_names(
                [self._resolve_step_names(s) for s in self.steps]
            )
            self._display = Display(
                steps=ordered, title="Pipeline", live=True
            )
        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        try:
            return await self._app.ainvoke(state)
        finally:
            if self._display is not None:
                self._display.stop()
```

The `run()` method needs the step names before building. Since `_build()` already resolves them, add a helper `_resolve_step_names` that extracts just the name from a step without instantiating:

```python
    def _resolve_step_names(self, step: Any) -> Any:
        if isinstance(step, list):
            return [self._resolve_step_names(s) for s in step]
        if isinstance(step, tuple):
            return step[0]
        base = step.rsplit("/", 1)[-1]
        return base
```

Note: This doesn't handle deduplication — the `_flatten_names` on these raw names won't match the deduped names from `_build`. A simpler approach: store the ordered names during `_build` as `self._ordered_names`, then use that in `run()`.

In `_build()`, after `self._validate_requires(ordered_names)`:

```python
        self._ordered_names = ordered_names
```

Then in `run()`:

```python
        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )
```

Remove the `_resolve_step_names` helper — it's not needed.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add langclaude/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire Display into Pipeline for live status tracking"
```

---

### Task 5: Wire Display into node printer (`base.py`)

**Files:**
- Modify: `langclaude/nodes/base.py:65-99`
- Modify: `langclaude/pipeline.py` (pass display to printer)

- [ ] **Step 1: Write failing test**

Add to `tests/test_display.py`:

```python
from langclaude.nodes.base import _make_printer, Verbosity


class TestMakePrinterWithDisplay:
    def test_verbose_printer_routes_to_display(self):
        d = Display(steps=["test_node"], title="T", live=False)
        printer = _make_printer(Verbosity.verbose, display=d)
        assert printer is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_display.py::TestMakePrinterWithDisplay -x -q --no-header`
Expected: `TypeError: _make_printer() got an unexpected keyword argument 'display'`

- [ ] **Step 3: Modify `_make_printer` to accept Display**

In `langclaude/nodes/base.py`, change the `_make_printer` signature and body:

```python
def _make_printer(verbosity: Verbosity, display: Any | None = None) -> MessageCallback | None:
    if verbosity == Verbosity.silent:
        return None
    show_usage = verbosity == Verbosity.verbose

    def _emit(node_name: str, line: str) -> None:
        if display is not None:
            display.node_output(node_name, line)
        else:
            print(f"[{node_name}] {line}", file=sys.stderr)

    def printer(node_name: str, message: Any) -> None:
        if isinstance(message, AssistantMessage):
            if show_usage:
                usage = _format_usage(getattr(message, "usage", None))
                if usage:
                    _emit(node_name, f"tokens{usage}")
            for block in message.content:
                if isinstance(block, TextBlock):
                    lines = block.text.splitlines()
                    max_lines = 5
                    for line in lines[:max_lines]:
                        _emit(node_name, line)
                    if len(lines) > max_lines:
                        _emit(node_name, f"... ({len(lines) - max_lines} more lines)")
                elif isinstance(block, ToolUseBlock):
                    args = ", ".join(f"{k}={str(v)!r}" for k, v in block.input.items())
                    _emit(node_name, f"→ {block.name}({args})")
                elif isinstance(block, ThinkingBlock):
                    _emit(node_name, "(thinking…)")
        elif isinstance(message, ResultMessage):
            if show_usage:
                cost = getattr(message, "total_cost_usd", None)
                cost_str = f" cost=${cost:.4f}" if cost is not None else ""
                usage_str = _format_usage(getattr(message, "usage", None))
                _emit(node_name, f"✓ done{cost_str}{usage_str}")
            else:
                _emit(node_name, "✓ done")

    return printer
```

The `[{node_name}]` prefix is no longer added in the printer for the Display path — Display's `node_output` already handles context via the output panel header.

- [ ] **Step 4: Wire Display into printer from Pipeline**

In `langclaude/pipeline.py`, modify `_apply_overrides` to inject the display into nodes that accept `on_message`. After the existing verbosity override block (lines 88-92), when verbosity is `verbose` and a display exists:

```python
        if "on_message" in params and "on_message" not in overrides:
            if self._display is not None and self.verbosity == Verbosity.verbose:
                from langclaude.nodes.base import _make_printer
                overrides["on_message"] = _make_printer(Verbosity.verbose, display=self._display)
```

But `self._display` is only set in `run()`, which happens after `_build()`. The `_apply_overrides` runs during `_build()`. So the display isn't available yet.

Fix: defer the printer creation. In `_make_tracking_wrap`, create the printer at call time (when the wrapper is invoked), not at build time. The simplest approach: don't touch `_apply_overrides` at all. Instead, in `_make_tracking_wrap`, override the node's `on_message` attribute directly:

In `_make_tracking_wrap`, at the top of the async `_wrapper`:

```python
            async def _wrapper(state):
                state = self._inject_prior_results(state, graph_name)

                if self._display is not None:
                    self._display.node_start(graph_name)
                    t0 = time.time()
                    if hasattr(node, 'on_message') and self.verbosity == Verbosity.verbose:
                        from langclaude.nodes.base import _make_printer
                        node.on_message = _make_printer(self.verbosity, display=self._display)

                result = await node(state)
                ...
```

Do the same for the sync wrapper.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add langclaude/nodes/base.py langclaude/pipeline.py tests/test_display.py
git commit -m "feat: route node streaming output through Display"
```

---

### Task 6: Wire Display into budget warnings

**Files:**
- Modify: `langclaude/budget.py:23-28`
- Modify: `langclaude/pipeline.py` (wire display.warn as on_warn)

- [ ] **Step 1: Write failing test**

Add to `tests/test_display.py`:

```python
class TestBudgetWarningWithDisplay:
    def test_warn_routes_through_display(self, capsys):
        d = Display(steps=[], title="T", live=False)
        d.warn("spent $0.0400 (80% of $0.0500 cap)")
        err = capsys.readouterr().err
        assert "spent $0.0400" in err
```

- [ ] **Step 2: Run test to verify it passes**

This test uses the existing `warn()` method. It should already pass. Verify:

Run: `.venv/bin/python -m pytest tests/test_display.py::TestBudgetWarningWithDisplay -x -q --no-header`
Expected: PASS

- [ ] **Step 3: Modify `default_on_warn` to accept optional Display**

In `langclaude/budget.py`, change `default_on_warn`:

```python
def default_on_warn(cost_usd: float, max_budget_usd: float, *, display: Any | None = None) -> None:
    pct = (cost_usd / max_budget_usd * 100) if max_budget_usd else 0
    msg = f"spent ${cost_usd:.4f} ({pct:.0f}% of ${max_budget_usd:.4f} cap)"
    if display is not None:
        display.warn(msg)
    else:
        print(f"[langclaude] WARNING: {msg}", file=sys.stderr)
```

- [ ] **Step 4: Wire in Pipeline**

In `langclaude/pipeline.py`'s `_apply_overrides`, after the model override block, add an `on_warn` override when a display is available. But again, `_display` isn't set at build time.

Instead, create a closure-based warn callback in `run()` and store it. Before `_app.ainvoke`:

```python
        # In run(), after creating self._display:
        if self._display is not None:
            self._warn_callback = lambda cost, cap: default_on_warn(cost, cap, display=self._display)
```

Then in `_apply_overrides`, check for `on_warn` param and use `self._warn_callback` if set. But `_apply_overrides` runs in `_build()`.

Simpler: the `BudgetTracker` is created inside `ClaudeAgentNode.__call__`. The `on_warn` is set at node construction. So we need to set it on the node at call time, same as `on_message`.

In `_make_tracking_wrap`'s async wrapper, add after the `on_message` override:

```python
                    if hasattr(node, 'on_warn') and node.on_warn is not None:
                        from langclaude.budget import default_on_warn
                        node.on_warn = lambda cost, cap: default_on_warn(cost, cap, display=self._display)
```

Actually, `on_warn` is a parameter on `ClaudeAgentNode.__init__`, stored as `self.on_warn`. The default is `None`, and `BudgetTracker` defaults to `default_on_warn` when `on_warn` is None. So we'd need to set it before `__call__`.

Cleaner approach: just override it on the node instance in the wrapper:

```python
                    if hasattr(node, 'on_warn'):
                        node.on_warn = lambda cost, cap: default_on_warn(cost, cap, display=self._display)
```

Do this for both async and sync wrappers.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add langclaude/budget.py langclaude/pipeline.py
git commit -m "feat: route budget warnings through Display"
```

---

### Task 7: Wire Display into interactive callbacks

**Files:**
- Modify: `langclaude/nodes/python_plan_feature.py:49-62`
- Modify: `langclaude/nodes/python_implement_feature.py:50-63`
- Modify: `langclaude/nodes/git_commit.py:52-67`
- Modify: `langclaude/permissions.py:128-140`

- [ ] **Step 1: Write failing test for plan_feature prompt_fn**

Add to `tests/test_interactive_nodes.py`:

```python
class TestPromptFnIntegration:
    @pytest.mark.asyncio
    async def test_plan_feature_uses_prompt_fn(self):
        calls = []

        async def mock_ask(plan):
            return None

        async def mock_prompt(text, content=None):
            calls.append(("prompt", text, content))
            return "y"

        node = python_plan_feature_node(ask_feedback=mock_ask)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "python_plan_feature_inner": "the plan",
                "last_cost_usd": 0.01,
            }
            result = await node({"working_dir": "/tmp", "task_description": "test"})

        assert result["python_plan_feature"] == "the plan"
```

This test verifies the existing behavior still works. The `prompt_fn` integration is about the default `ask_*_via_stdin` functions accepting a `prompt_fn` parameter, which is only used when Pipeline wires it in.

- [ ] **Step 2: Modify `ask_plan_feedback_via_stdin`**

In `langclaude/nodes/python_plan_feature.py`, change the callback signature to accept an optional `prompt_fn`:

```python
PromptFn = Callable[[str, str | None], str]


def _default_prompt(text: str, content: str | None = None) -> str:
    if content is not None:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(content, file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
    return input(f"\n{text} ")


async def ask_plan_feedback_via_stdin(
    plan: str,
    prompt_fn: PromptFn | None = None,
) -> str | None:
    if not sys.stdin.isatty():
        return None
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(prompt, "[plan] Approve? (y)es or provide feedback:", plan)
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a
```

Update the `AskFeedback` type and the `python_plan_feature_node` factory to thread through `prompt_fn`:

```python
AskFeedback = Callable[[str, PromptFn | None], Awaitable[str | None]]
```

In the factory, pass `prompt_fn=None` through to `ask_feedback`:

```python
            feedback = await ask_feedback(plan, None)
```

- [ ] **Step 3: Modify `ask_impl_feedback_via_stdin`**

In `langclaude/nodes/python_implement_feature.py`, apply the same pattern:

```python
PromptFn = Callable[[str, str | None], str]


def _default_prompt(text: str, content: str | None = None) -> str:
    if content is not None:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(content, file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
    return input(f"\n{text} ")


async def ask_impl_feedback_via_stdin(
    summary: str,
    prompt_fn: PromptFn | None = None,
) -> str | None:
    if not sys.stdin.isatty():
        return None
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(prompt, "[implement] Approve? (y)es or describe what to fix:", summary)
    a = answer.strip()
    if a.lower() in ("y", "yes", ""):
        return None
    return a
```

Update `AskFeedback` and the factory call similarly.

- [ ] **Step 4: Modify `ask_push_via_stdin`**

In `langclaude/nodes/git_commit.py`:

```python
PromptFn = Callable[[str, str | None], str]


def _default_prompt(text: str, content: str | None = None) -> str:
    if content is not None:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(content, file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
    return input(f"\n{text} ")


async def ask_push_via_stdin(
    summary: str,
    prompt_fn: PromptFn | None = None,
) -> Literal["push", "skip", "feedback"] | str:
    if not sys.stdin.isatty():
        return "push"
    prompt = prompt_fn or _default_prompt
    answer = await asyncio.to_thread(prompt, "[git_commit] (p)ush / (s)kip push / or provide feedback:", summary)
    a = answer.strip()
    if a.lower() in ("p", "push", "y", "yes", ""):
        return "push"
    if a.lower() in ("s", "skip", "n", "no"):
        return "skip"
    return a
```

Update `AskPush` type similarly.

- [ ] **Step 5: Modify `ask_via_stdin`**

In `langclaude/permissions.py`:

```python
async def ask_via_stdin(tool_name: str, input_data: dict[str, Any], prompt_fn: Any | None = None) -> bool:
    if not sys.stdin.isatty():
        return False

    summary = ", ".join(f"{k}={v!r}" for k, v in list(input_data.items())[:3])
    text = f"[langclaude] Allow {tool_name}({summary})? [y/N]:"
    if prompt_fn is not None:
        answer = await asyncio.to_thread(prompt_fn, text, None)
    else:
        answer = await asyncio.to_thread(input, f"\n{text} ")
    return answer.strip().lower() in ("y", "yes")
```

- [ ] **Step 6: Run existing tests to verify no breakage**

Run: `.venv/bin/python -m pytest tests/test_interactive_nodes.py tests/test_permissions.py -x -q --no-header`
Expected: all tests pass. The existing tests pass `ask_feedback`/`ask_push` callbacks with the old signature (single arg), but those callbacks don't use `prompt_fn`, so the default parameter handles backward compat.

Wait — the existing tests pass custom callbacks with a single parameter. The new `AskFeedback` type expects `(str, PromptFn | None)`. The custom test callbacks like `async def mock_feedback(plan)` won't match.

Fix: keep the `AskFeedback` type accepting a single string. The `prompt_fn` is only used by the *default* callbacks (`ask_plan_feedback_via_stdin` etc.). Custom callbacks implement their own prompting. So `prompt_fn` is an argument to the default callbacks, not to the type alias.

The factory call changes from `await ask_feedback(plan)` to `await ask_feedback(plan)` — no change needed. The `prompt_fn` is passed to the default callback at *construction* time, not at call time.

Revised approach: use `functools.partial` or a closure. The factory accepts `prompt_fn` and creates a bound version of the default callback:

```python
def python_plan_feature_node(
    *,
    ...
    ask_feedback: AskFeedback = ask_plan_feedback_via_stdin,
    prompt_fn: PromptFn | None = None,
    ...
):
    if prompt_fn is not None and ask_feedback is ask_plan_feedback_via_stdin:
        from functools import partial
        ask_feedback = partial(ask_plan_feedback_via_stdin, prompt_fn=prompt_fn)
    ...
```

This way `AskFeedback` stays `Callable[[str], Awaitable[str | None]]` and existing tests are untouched.

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add langclaude/nodes/python_plan_feature.py langclaude/nodes/python_implement_feature.py langclaude/nodes/git_commit.py langclaude/permissions.py
git commit -m "feat: add prompt_fn support to interactive callbacks"
```

---

### Task 8: Wire prompt_fn from Pipeline into interactive nodes

**Files:**
- Modify: `langclaude/pipeline.py`

The interactive nodes (`python_plan_feature`, `python_implement_feature`, `git_commit`) accept `prompt_fn` in their factory. Pipeline needs to pass `display.prompt` as `prompt_fn` when constructing these nodes.

- [ ] **Step 1: Pass prompt_fn through config overrides**

In `langclaude/pipeline.py`'s `_apply_overrides`, after the model override:

```python
        if "prompt_fn" in params and "prompt_fn" not in overrides:
            if self._display is not None:
                overrides["prompt_fn"] = self._display.prompt
```

But `_display` isn't set at build time. Same problem again.

Fix: set `prompt_fn` on the node at call time in `_make_tracking_wrap`, same pattern as `on_message` and `on_warn`. But `prompt_fn` is consumed at factory construction, not at call time — it's baked into the closure.

Better fix: thread it through state. Add a `_display_prompt_fn` key to state in `run()`:

No — that pollutes state with infrastructure.

Simplest fix: build the graph lazily. Move `_build()` from `__init__` to `run()`, after `_display` is set. Then `_apply_overrides` can read `self._display`.

Actually, `_build()` only needs to happen once. If we move it to `run()` we'd need a guard. But `run()` might be called multiple times.

Better approach: don't use the factory's `prompt_fn` parameter at all from Pipeline. Instead, override the `ask_feedback`/`ask_push` callback on the node instance at call time in `_make_tracking_wrap`, the same way we override `on_message` and `on_warn`.

In `_make_tracking_wrap`'s async wrapper:

```python
                if self._display is not None:
                    self._display.node_start(graph_name)
                    t0 = time.time()
                    if hasattr(node, 'on_message') and self.verbosity == Verbosity.verbose:
                        from langclaude.nodes.base import _make_printer
                        node.on_message = _make_printer(self.verbosity, display=self._display)
                    if hasattr(node, 'on_warn'):
                        from langclaude.budget import default_on_warn
                        node.on_warn = lambda cost, cap: default_on_warn(cost, cap, display=self._display)
```

But interactive nodes are closures (functions), not class instances. They don't have `ask_feedback` as an attribute — it's captured in the closure.

The cleanest approach that avoids all timing problems: **store prompt_fn in state**. This is the same pattern as `working_dir` and `task_description` — infrastructure that nodes can read from state.

In `run()`, after creating display:

```python
        if self._display is not None:
            state["_prompt_fn"] = self._display.prompt
```

Then in the default callbacks, check state. But the callbacks don't have access to state — they only receive the plan/summary string.

Final approach: accept that the `prompt_fn` factories need the display at construction time. Build the graph lazily:

```python
    def __init__(self, ...):
        ...
        self._display: Display | None = None
        self._requires_map: dict[str, list[str]] = {}
        self._register_custom_nodes()
        # Don't build yet — deferred to run() so _display is available

    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            ...create display...
        self._app = self._build()  # Now _display is set
        ...
```

In `_apply_overrides`, inject `prompt_fn`:

```python
        if "prompt_fn" in params and "prompt_fn" not in overrides:
            if self._display is not None:
                overrides["prompt_fn"] = self._display.prompt
```

This is the cleanest solution. The only behavioral change is that `_build()` happens in `run()` instead of `__init__`. Validation that currently fails at construction (bad step names) would now fail at `run()` time instead.

- [ ] **Step 2: Move `_build()` call from `__init__` to `run()`**

In `langclaude/pipeline.py`, `__init__`:

Remove `self._app = self._build()`. Add `self._app = None`.

In `run()`:

```python
    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )

        if self._app is None:
            self._app = self._build()

        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        try:
            return await self._app.ainvoke(state)
        finally:
            if self._display is not None:
                self._display.stop()
```

But `_ordered_names` is set in `_build()`. So we need to call `_build()` before creating Display. Reorder:

```python
    async def run(self, **extra: Any) -> dict[str, Any]:
        if self._app is None:
            self._app = self._build()

        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )
        ...
```

But then `_display` isn't set when `_apply_overrides` runs inside `_build()`. We need a two-pass approach: first build to get names, then set display, then rebuild with prompt_fn. That's wasteful.

Simplest working approach: extract `_ordered_names` computation from `_build()` into a separate step during `__init__`:

```python
    def __init__(self, ...):
        ...
        self._display: Display | None = None
        self._requires_map: dict[str, list[str]] = {}
        self._register_custom_nodes()
        self._ordered_names = self._compute_ordered_names()
        # _app built lazily in run()
        self._app: Any | None = None

    def _compute_ordered_names(self) -> list[str]:
        seen: dict[str, int] = {}
        resolved = [self._resolve_step_for_names(s, seen) for s in self.steps]
        return self._flatten_names(resolved)

    def _resolve_step_for_names(self, step: Any, seen: dict[str, int]) -> Any:
        if isinstance(step, list):
            return [self._resolve_step_for_names(s, seen) for s in step]
        if isinstance(step, tuple):
            graph_name = step[0]
            seen[graph_name] = seen.get(graph_name, 0) + 1
            return (graph_name, None)
        base = step.rsplit("/", 1)[-1]
        graph_name = self._dedup_name(base, seen)
        return (graph_name, None)
```

Then `run()`:

```python
    async def run(self, **extra: Any) -> dict[str, Any]:
        if self.verbosity != Verbosity.silent:
            self._display = Display(
                steps=self._ordered_names, title="Pipeline", live=True
            )
        if self._app is None:
            self._app = self._build()
        ...
```

Now `_display` is set before `_build()`, so `_apply_overrides` can read it.

- [ ] **Step 3: Add prompt_fn injection in `_apply_overrides`**

```python
        if "prompt_fn" in params and "prompt_fn" not in overrides:
            if self._display is not None:
                overrides["prompt_fn"] = self._display.prompt
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass. Some tests construct Pipeline in `__init__` and check `_app` — those now get `_app = None` until `run()`. Fix any tests that access `p._app is not None` by either calling `run()` or checking `_ordered_names` instead.

The existing tests that check `p._app is not None`:
- `test_parallel_steps`: `assert p._app is not None`
- `test_config_overrides`: `assert p._app is not None`
- `test_aliased_tuple_step`: `assert p._app is not None`
- `test_duplicate_step_auto_suffixed`: `assert p._app is not None`
- `test_custom_node_inline`: `assert p._app is not None`

Update these to assert `p._ordered_names` is a non-empty list instead:

```python
    def test_parallel_steps(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[["python_lint", "python_format"]],
        )
        assert len(p._ordered_names) > 0
```

- [ ] **Step 5: Run all tests again**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add langclaude/pipeline.py tests/test_pipeline.py
git commit -m "feat: inject Display.prompt into interactive node factories"
```

---

### Task 9: Wire Display into final results

**Files:**
- Modify: `langclaude/graphs/python_quality_gate.py:68-84`
- Modify: `langclaude/graphs/python_new_feature.py:57-70`

- [ ] **Step 1: Modify `python_quality_gate.py` main()**

Replace the manual `print()` calls with `Display.print_results()`:

```python
from langclaude.display import Display


async def main(
    working_dir: str,
    mode: str = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(
        working_dir, mode=mode, base_ref=base_ref, verbosity=verbosity
    )
    final = await pipeline.run()

    node_costs = final.get("node_costs", {})
    display = Display(steps=list(node_costs.keys()), title="Quality Gate", live=False)
    display.print_results(node_costs)
```

- [ ] **Step 2: Modify `python_new_feature.py` main()**

```python
from langclaude.display import Display


async def main(
    working_dir: str,
    task: str,
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(working_dir, task, base_ref=base_ref, verbosity=verbosity)
    final = await pipeline.run()

    node_costs = final.get("node_costs", {})
    display = Display(steps=list(node_costs.keys()), title="Results", live=False)
    display.print_results(node_costs)
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add langclaude/graphs/python_quality_gate.py langclaude/graphs/python_new_feature.py
git commit -m "feat: use Display.print_results for final cost tables"
```

---

### Task 10: Export Display and final cleanup

**Files:**
- Modify: `langclaude/__init__.py`

- [ ] **Step 1: Add Display to exports**

In `langclaude/__init__.py`, add the import:

```python
from langclaude.display import Display
```

Add `"Display"` to `__all__` (alphabetically, after `"DEFAULT"`).

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add langclaude/__init__.py
git commit -m "feat: export Display from langclaude package"
```

---

### Task 11: End-to-end verification

- [ ] **Step 1: Run full test suite one final time**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass.

- [ ] **Step 2: Verify imports work**

Run: `.venv/bin/python -c "from langclaude import Display, Pipeline, Verbosity; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 3: Verify rich renders in terminal**

Run: `.venv/bin/python -c "from langclaude.display import Display; d = Display(steps=['a','b','c'], title='Test', live=True); d.node_start('a'); import time; time.sleep(1); d.node_done('a', 1.0, 0.01); d.node_start('b'); time.sleep(1); d.node_done('b', 1.0); d.node_start('c'); time.sleep(0.5); d.node_done('c', 0.5); d.stop()"`

Expected: see a live-updating table with spinner on active row, green checkmarks on completed rows.
