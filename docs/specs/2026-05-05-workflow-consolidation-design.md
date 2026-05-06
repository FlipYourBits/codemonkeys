# Workflow Consolidation

Merge the two parallel review systems (`run_review.py` monolith and `workflows/` engine) into one. Rebuild the agent runner and display from scratch; keep the workflow engine, phase library, compositions, and event system as-is.

## Problem

Two implementations of the same review pipeline exist:

1. **`run_review.py`** (~1070 lines) — the original CLI monolith with its own agent execution, display rendering, logging, and NLP triage.
2. **`workflows/`** — a structured system with engine, phases, events, compositions, and a phase library. More features (mode-aware prompts, mechanical audits, dedup, parallel fixing) but missing NLP triage, per-agent display cards, and debug logging.

They share agent definitions but have independent execution paths, independent token tracking, and independent display code. Adding cross-cutting features (like a token budget) means implementing them twice.

## Approach

Rebuild `AgentRunner` and the display from scratch. Port `run_review.py`'s three missing features into the workflow system. Reduce `run_review.py` to a thin CLI wrapper. Delete the TUI, the duplicate `workflows/review.py`, and `WorkflowProgress`.

## Design

### New `AgentRunner` (`core/runner.py`)

Single way to run agents everywhere. Combines the current runner's SDK streaming with `run_review._run_agent()`'s logging and callbacks.

**Constructor:**

```python
AgentRunner(cwd: str, emitter: EventEmitter | None = None, log_dir: Path | None = None)
```

**Return type — `RunResult`:**

```python
@dataclass
class RunResult:
    text: str                           # raw text result
    structured: dict[str, Any] | None   # parsed structured output (if any)
    usage: dict[str, Any]               # final token usage
    cost: float | None                  # USD cost
    duration_ms: int                    # wall-clock time
```

**Behavior:**

- Streams `claude_agent_sdk.query()` messages, accumulates tokens per-turn, tracks per-subagent tokens.
- Emits `AGENT_STARTED`, `AGENT_PROGRESS`, `AGENT_COMPLETED` events via the `EventEmitter`. If no emitter provided, events are silently skipped.
- Writes debug logs when `log_dir` is set:
  - `.log` — JSONL of all raw SDK messages (ported from `run_review._run_agent()`)
  - `.md` — readable file with system prompt, user prompt, and structured output
- Extracts structured output automatically — no more per-phase `getattr` / `json.loads` / `model_validate` boilerplate.
- Calls `sandbox.restrict()` on first run.
- Does **not** own a display. No `Live`, no `_Display` class. Display is handled by a separate subscriber.

### Unified CLI Display (`workflows/display.py`)

Replaces both `WorkflowProgress` (phase checklist) and `run_review.py`'s agent cards. Subscribes to events from the `EventEmitter` — no direct coupling to the runner or engine.

**Layout** — single Rich `Live` context for the whole workflow run:

- Top: phase checklist (pending/running/done with spinners)
- Middle: agent cards within the active phase (name, status, activity, tokens, tool calls) — same data as `run_review.py` streams today
- Shows mechanical tool results, fix progress, findings counts
- Cumulative token total visible at all times
- Agent cards clear between phases

**Event subscriptions:**

- `PHASE_STARTED`, `PHASE_COMPLETED` → phase checklist
- `AGENT_STARTED`, `AGENT_PROGRESS`, `AGENT_COMPLETED` → agent cards
- `MECHANICAL_TOOL_*` → tool results under mechanical_audit
- `FIX_PROGRESS` → per-file fix status
- `WORKFLOW_COMPLETED`, `WORKFLOW_ERROR` → stop display

**Event payload additions:**

- `AgentStartedPayload` gains `model: str` and `files_label: str` fields so the display can show which files and model each agent uses.

### NLP Triage (`phase_library/action.py`)

The existing `triage()` phase gains NLP interpretation. When the triage phase is a `GATE` and receives a string as user input (rather than a pre-built `FixRequest` list), it dispatches a haiku agent via `AgentRunner` to translate the natural language into fix selections.

```python
if isinstance(ctx.user_input, str):
    fix_requests = await _nlp_triage(ctx.user_input, all_findings, ctx)
    return {"fix_requests": fix_requests}
```

The `_nlp_triage()` helper is ported from `run_review.nlp_triage()` — same prompt, same JSON parsing, same index-to-finding mapping.

### Thin CLI Wrapper (`run_review.py`)

Shrinks from ~1070 lines to ~100 lines. Responsibilities:

1. Parse CLI args (`--files`, `--diff`, `--repo`, `--auto-fix`, `--graph`)
2. Pick the right workflow composition from `compositions.py`
3. Build `ReviewConfig` and `WorkflowContext`
4. Create `EventEmitter`, attach `WorkflowDisplay`
5. Handle gates — listen for `WAITING_FOR_USER`, prompt user, call `engine.resolve_gate()`
6. Call `engine.run()`
7. Init log dir, store it on `WorkflowContext` so phase functions can pass it to `AgentRunner`

Mode selection prompt (`_select_mode()`) stays in the CLI since it runs before the workflow starts.

### `WorkflowContext` Additions (`workflows/phases.py`)

`WorkflowContext` gains a `log_dir: Path | None` field. The CLI sets it at construction. Phase functions use `ctx.log_dir` and `ctx.emitter` (already exists) when constructing `AgentRunner`:

```python
runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
```

### Engine Changes (`workflows/engine.py`)

One minor change: create the gate future *before* emitting `WAITING_FOR_USER`, so the event handler can call `resolve_gate()`:

```python
# Before (current):
self._emitter.emit(EventType.WAITING_FOR_USER, ...)
self._gate_future = loop.create_future()

# After:
self._gate_future = loop.create_future()
self._emitter.emit(EventType.WAITING_FOR_USER, ...)
```

The CLI's gate handler uses `run_in_executor` to run blocking `console.input()` without stalling the event loop, then calls `resolve_gate()` via `call_soon_threadsafe`.

### `implement.py` Fix

Currently imports from `workflows/review.py` (which is being deleted). Its `_auto_review` phase changes to import phase functions from `phase_library` instead — same functions, different import path.

## Deletions

| Target | Reason |
|---|---|
| `tui/` (entire directory) | No longer needed — future TUI subscribes to events |
| `cli.py` | TUI entry point |
| `workflows/progress.py` | Replaced by `workflows/display.py` |
| `workflows/review.py` | Duplicate of `phase_library/` implementations |
| `run_review.py` (~970 lines) | Everything except CLI wrapper |
| `core/runner.py` `_Display` class | Replaced by event emission |

## What Stays Unchanged

- `workflows/engine.py` — one line reorder
- `workflows/events.py` — minor payload additions
- `workflows/phases.py`
- `workflows/compositions.py`
- `workflows/graph.py`
- `workflows/phase_library/*` — NLP triage added to `action.py`
- `core/sandbox.py`
- All agent definitions (`core/agents/`)
- All prompts (`core/prompts/`)
- All schemas (`artifacts/schemas/`)

## Future: Token Budget

With consolidation done, the `--max-tokens` feature becomes straightforward:

- `AgentRunner` tracks cumulative tokens and emits them with every `AGENT_PROGRESS` event.
- `WorkflowDisplay` shows a yellow warning banner when the budget is exceeded.
- The engine checks cumulative tokens after each phase completes. If over budget, it injects a gate prompting the user to continue or abort.
- Single implementation, one place to maintain.
