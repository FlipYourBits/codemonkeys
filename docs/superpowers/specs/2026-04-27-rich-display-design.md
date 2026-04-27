# Rich Display for langclaude

## Problem

All pipeline output is plain white `print()` to stderr. Node progress, streaming output, budget warnings, interactive prompts, and final results all use unstructured text. It works but looks unprofessional and makes long pipelines hard to follow.

## Solution

Add a `Display` class backed by `rich` that renders a live-updating pipeline table with a collapsing output panel. All terminal output flows through this single module.

## New dependency

`rich>=13.0,<14` added to `dependencies` in pyproject.toml (required, not optional).

## Module: `langclaude/display.py`

### `Display` class

Owns a `rich.console.Console(stderr=True)` and a `rich.live.Live` region.

**Constructor:** `Display(steps: list[str], title: str, live: bool = True)`
- `steps` — ordered list of graph names, used to pre-populate all table rows.
- `title` — pipeline name shown as table title (e.g. "Python Quality Gate").
- `live=False` — non-TTY / CI fallback. Uses `Console.print()` instead of Live redraw.

**Public methods:**

| Method | Behavior |
|--------|----------|
| `node_start(name)` | Marks row as running with animated spinner. |
| `node_output(name, line)` | Appends to the active output panel (last 5 lines visible). |
| `node_done(name, elapsed, cost)` | Row turns green with checkmark, elapsed time, optional cost. Output panel clears. |
| `node_skip(name)` | Row shows dimmed dash. |
| `prompt(text, content=None) -> str` | Stops Live, optionally prints `content` (e.g. plan text) in a styled panel, shows prompt via `Console.input()`, resumes Live. |
| `warn(text)` | Yellow warning line. |
| `print_results(table_data)` | Renders a `rich.table.Table` for the final cost/results summary. |
| `stop()` | Tears down Live cleanly. |

### Live layout

Two regions stacked vertically via `rich.console.Group`:
- **Top:** Pipeline table. All steps shown from the start. Pending rows are dim, active row has a spinner, completed rows are green with timing.
- **Bottom:** Output panel for the active node. Shows last 5 lines of streaming output (tool calls, text blocks, thinking). Clears when the node completes and the next starts.

### Non-TTY fallback (`live=False`)

When `live=False`, methods degrade to styled `Console.print()`:
- `node_start` prints `● {name}...`
- `node_done` prints `✓ {name} done ({elapsed}s, ${cost})`
- `node_output` prints `  [{name}] {line}`
- `prompt` uses `Console.input()`
- No Live context is created.

## Integration points

### Pipeline (`pipeline.py`)

- Creates and owns the `Display` instance at the start of `run()`.
- Passes `steps` (the ordered list of graph names from `_flatten_names`).
- `_make_tracking_wrap` calls `display.node_start()` / `display.node_done()` instead of `print()`.
- Passes the display to `_make_printer` so node streaming output routes through `display.node_output()`.
- Passes `display.prompt` to interactive node callbacks.
- Calls `display.stop()` after the pipeline completes.

### Node printer (`nodes/base.py`)

- `_make_printer` accepts an optional `Display` parameter.
- When a display is provided, it calls `display.node_output(name, formatted_line)` instead of `print()`.
- Formatting logic (tool call arrows, thinking indicator, text truncation) stays in `_make_printer` — it formats the string, Display renders it.

### Budget warning (`budget.py`)

- `default_on_warn` accepts an optional `Display` parameter.
- Calls `display.warn(text)` instead of `print()`.

### Interactive callbacks

All three prompt sites accept a `prompt_fn` parameter (defaults to raw `input` for backward compat). Pipeline injects `display.prompt` when a display is active.

| File | Callback | Current | New |
|------|----------|---------|-----|
| `nodes/python_plan_feature.py` | `ask_plan_feedback_via_stdin` | `input()` | `prompt_fn()` |
| `nodes/python_implement_feature.py` | (same pattern) | `input()` | `prompt_fn()` |
| `nodes/git_commit.py` | `ask_push_via_stdin` | `input()` | `prompt_fn()` |
| `permissions.py` | `ask_via_stdin` | `input()` | `prompt_fn()` |

### Final results (`graphs/*.py`)

`main()` in `python_quality_gate.py` and `python_new_feature.py` call `display.print_results()` instead of manual `print()` formatting. This renders a styled `rich.table.Table`.

## Verbosity mapping

| Level | Display | Table | Output panel | Token counts |
|-------|---------|-------|-------------|--------------|
| `silent` | No Display created | — | — | — |
| `normal` | `live=True` | Yes | Suppressed | No |
| `verbose` | `live=True` | Yes | Active (last 5 lines) | Yes |

## Files changed

| File | Change |
|------|--------|
| `langclaude/display.py` | New — `Display` class, all rich rendering. |
| `langclaude/pipeline.py` | Create Display, wire into tracking wraps and printers. |
| `langclaude/nodes/base.py` | `_make_printer` accepts optional Display. |
| `langclaude/budget.py` | `default_on_warn` accepts optional Display. |
| `langclaude/nodes/python_plan_feature.py` | Callback uses `prompt_fn`. |
| `langclaude/nodes/python_implement_feature.py` | Callback uses `prompt_fn`. |
| `langclaude/nodes/git_commit.py` | Callback uses `prompt_fn`. |
| `langclaude/permissions.py` | Callback uses `prompt_fn`. |
| `langclaude/graphs/python_quality_gate.py` | Use `display.print_results()`. |
| `langclaude/graphs/python_new_feature.py` | Use `display.print_results()`. |
| `pyproject.toml` | Add `rich>=13.0,<14` to dependencies. |
| `tests/test_display.py` | New — tests for Display (non-TTY mode). |

## Not changed

Node registration, graph wiring, state schema, CLI argument parsing, `Verbosity` enum.
