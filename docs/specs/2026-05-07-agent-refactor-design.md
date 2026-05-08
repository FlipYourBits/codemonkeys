# Agent Refactor: Pure Definitions + Shared Display

## Goal

Separate agent definitions from formatting/display logic. Agent files become pure declarations (prompt, schema, factory). Shared formatting code lives in one place. CLI files stay as the workflow/pipeline layer but get thinner by importing shared display utilities.

## What Changes

### 1. Agent files become pure definitions

**`agents/review_auditor.py`** — the main target. Currently has ~120 lines of formatting code (`_format_tool_input`, `_extract_tool_result`, `_format_event_trace`) and ~30 lines of actual agent definition.

After refactor:
- Remove all formatting functions
- Factory signature changes from `make_review_auditor(result: RunResult)` to `make_review_auditor(trace: str, findings_json: str)`
- The factory just interpolates pre-formatted strings into its prompt template
- Schemas (`AuditFinding`, `ReviewAudit`) and constants (`Verdict`, `Category`, `Severity`) stay

**`agents/python_file_reviewer.py`** — already clean, no changes.

**`agents/fixer.py`** — already clean, no changes.

### 2. Shared display module

**Create `display/formatting.py`** — single source for all formatting:

| Function | Replaces | Used by |
|----------|----------|---------|
| `format_tool_call(tool_name, tool_input) -> str` | Inline formatting in `run_review.py`, `fix.py`, `review_auditor.py` | stdout printer, event trace builder, frontend (conceptually) |
| `format_tool_result(data) -> str` | `review_auditor._extract_tool_result` + `run_review._tool_result_hint` | Event trace builder, stdout printer |
| `format_event_trace(events) -> str` | `review_auditor._format_event_trace` | `run_review.py` (when building auditor input) |
| `severity_style(severity) -> str` | Duplicated in `run_review.py` and `fix.py` | CLI summary printing |

**Create `display/stdout.py`** — single copy of the stdout printer:

| Function | Replaces |
|----------|----------|
| `make_stdout_printer() -> EventHandler` | Identical ~100-line functions in both `run_review.py` and `fix.py` |

The stdout printer imports `format_tool_call` from `formatting.py` instead of inline formatting.

**`display/logger.py`** — no changes (already clean).

**`display/live.py`** — no changes (already clean).

### 3. CLI files become thin pipelines

**`run_review.py`** after refactor:
- File discovery functions stay (they're CLI-specific)
- `_make_stdout_printer` removed (import from `display/stdout.py`)
- `_severity_style` removed (import from `display/formatting.py`)
- `_tool_result_hint`, `_system_message_label` removed (used by stdout printer, now in `display/stdout.py`)
- Summary printing functions stay (CLI-specific Rich table rendering)
- `run_review()` pipeline logic stays but the auditor creation changes:

```python
# Before: auditor formats its own trace internally
auditor = make_review_auditor(result)

# After: caller formats trace, passes strings to auditor
trace = format_event_trace(result.events)
findings_json = result.output.model_dump_json(indent=2)
auditor = make_review_auditor(trace=trace, findings_json=findings_json)
```

**`fix.py`** after refactor:
- `_make_stdout_printer` removed (import from `display/stdout.py`)
- `_severity_style` removed (import from `display/formatting.py`)
- Finding loading, selection, and result printing stay (CLI-specific)
- `run_fix()` stays as-is (already simple)

### 4. Dashboard integration

The dashboard server (`dashboard/server.py`) can use the same shared formatting when it needs to chain agents. When a user chains reviewer → auditor from the dashboard:

```python
trace = format_event_trace(result.events)
findings_json = result.output.model_dump_json(indent=2)
auditor = make_review_auditor(trace=trace, findings_json=findings_json)
```

Same code path as the CLI.

## File inventory

### New files
- `display/formatting.py` — shared formatting functions
- `display/stdout.py` — shared stdout printer

### Modified files
- `agents/review_auditor.py` — remove formatting, change factory signature
- `run_review.py` — import shared display, slim down
- `fix.py` — import shared display, slim down

### Unchanged files
- `agents/python_file_reviewer.py`
- `agents/fixer.py`
- `core/events.py`
- `core/runner.py`
- `core/types.py`
- `core/hooks.py`
- `display/logger.py`
- `display/live.py`
- `dashboard/*`

## What this does NOT do

- No workflow abstraction layer — CLIs are the workflows
- No DAG runner — chaining is explicit sequential code
- No changes to agent schemas or event types
- No dashboard UI changes
