# Codemonkeys Python Package Architecture

## Overview

Codemonkeys is a developer tool for running AI-powered code analysis and implementation workflows locally before pushing code. It uses a producer/consumer agent architecture with structured JSON artifacts as the contract between phases, orchestrated by a workflow engine, and presented through a beautiful Textual TUI.

## Core Principles

- **Artifact-driven phases with a human gate.** Analyzer agents produce structured JSON findings/plans. The developer reviews them in the TUI and selects what to act on. Executor agents consume the selections and make changes.
- **Backend/frontend separation.** The core package (agents, workflows, artifacts) is a self-contained API. The TUI is the first frontend but any UI (PyQt, web) could consume the same API.
- **Sandboxed by default.** The entire process tree is filesystem-sandboxed on launch — no agent or subprocess can write outside the project directory (plus `/tmp`, `/dev`, and Claude CLI state dirs).
- **Deterministic workflows.** Workflows are state machines with defined phases and transitions. The TUI renders state — it doesn't drive logic.

## Architecture Layers

```
┌─────────────────────────────────┐
│  TUI (Textual)                  │  renders state, forwards user input
├─────────────────────────────────┤
│  Workflows (state machines)     │  orchestrates phases, manages artifacts
├─────────────────────────────────┤
│  Core (agents, runner, sandbox) │  executes agents, produces results
└─────────────────────────────────┘
```

Strict dependency direction: each layer depends only on the one below. The TUI never touches agents directly. The core layer has no knowledge of workflows or UI.

## Agent Model

### Two Categories

| | Analyzers | Executors |
|---|---|---|
| **Input** | Source code / codebase | Artifact JSON from an analyzer |
| **Output** | Structured JSON artifacts | Code changes |
| **File access** | Read-only | Read + write |
| **Scope** | One file or one topic | One file's worth of work |
| **Examples** | File reviewer, README reviewer, changelog reviewer, feature planner, bug fix planner | Code fixer, feature implementer, bug fixer |

### Agent Registry

Agents declare their I/O so the system wires them together automatically:

```python
class AgentRole(Enum):
    ANALYZER = "analyzer"
    EXECUTOR = "executor"

class AgentSpec:
    name: str                          # "python-file-reviewer"
    role: AgentRole
    description: str                   # shown in TUI
    produces: type[BaseModel] | None   # output Pydantic model (analyzers)
    consumes: type[BaseModel] | None   # input Pydantic model (executors)
    scope: Literal["file", "project"]  # per-file or whole-project
    make: Callable                     # factory function
```

An executor can handle an artifact if its `consumes` type matches the analyzer's `produces` type. The TUI reads the registry to know what to offer and how to connect them.

### Structured Output

Agents use the Claude Agent SDK's `output_format` parameter for structured output:

1. Define a Pydantic model with `Field(description=...)` on every field
2. Pass `output_format={"type": "json_schema", "schema": Model.model_json_schema()}` to the runner
3. Agent returns `structured_output` on the result — validate with `Model.model_validate()`
4. Write to artifact store with `Model.model_dump_json()`

The Pydantic models serve triple duty: artifact schema, agent output schema, and typed Python objects in the backend.

## Artifact System

Artifacts live in `.codemonkeys/` inside the project directory (gitignored).

```
.codemonkeys/
  review/
    2026-05-04T14-30-00/
      findings/
        src__auth__login.py.json
        src__auth__middleware.py.json
      mechanical.json
  implement/
    2026-05-04T15-00-00/
      plan.json
      approved-plan.json
      results.json
```

### Artifact Schemas

All artifact types are Pydantic models with descriptive fields. Example:

```python
class Finding(BaseModel):
    file: str = Field(description="Relative path to the file containing the issue")
    line: int | None = Field(description="Line number where the issue occurs, or null if file-level")
    severity: Literal["high", "medium", "low", "info"] = Field(description="Impact severity")
    category: Literal["quality", "security", "bug", "style"] = Field(description="Type of issue found")
    title: str = Field(description="Short summary of the issue")
    description: str = Field(description="Detailed explanation of what's wrong and why it matters")
    suggestion: str | None = Field(description="Concrete suggestion for how to fix the issue")
```

Timestamped directories preserve history of past runs. The TUI can show recent runs and let users revisit old findings.

## Workflow Engine

A workflow is a state machine defined by phases, transitions, and artifacts.

### Phase Types

- **Automated** — agents run without intervention (review dispatch, verification)
- **Interactive** — back-and-forth with user (feature planning)
- **Gate** — user reviews artifacts and makes selections (triage findings, approve plan)

### Review Workflow

```
[Discover]     automated — find files to review, run ruff/pyright/pytest
    ↓ artifacts: file list, mechanical check results
[Review]       automated — dispatch per-file reviewer agents in parallel
    ↓ artifacts: per-file findings JSON
[Triage]       gate — user sees findings in TUI, selects which to fix
    ↓ artifacts: fix request JSON (selected findings)
[Fix]          automated — dispatch one fixer agent per file
    ↓ artifacts: fix results JSON
[Verify]       automated — re-run checks on changed files
    ↓ artifacts: verification results
[Report]       automated — summarize what was fixed, what remains
```

### Implement Workflow

```
[Plan]         interactive — discuss feature, clarify requirements
    ↓ artifacts: plan JSON
[Approve]      gate — user reviews plan in TUI, approves or edits
    ↓ artifacts: approved plan JSON
[Implement]    automated — dispatch implementer agent with plan
    ↓ artifacts: implementation results JSON
[Verify]       automated — run tests, ruff, pyright
    ↓ artifacts: verification results
[Report]       automated — summarize what was implemented
```

### Events

The workflow engine emits typed events for UI consumption:

```python
class EventType(Enum):
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    AGENT_STARTED = "agent_started"
    AGENT_PROGRESS = "agent_progress"
    AGENT_COMPLETED = "agent_completed"
    FINDING_ADDED = "finding_added"
    WAITING_FOR_USER = "waiting_for_user"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ERROR = "workflow_error"
```

Events carry typed Pydantic payloads. The TUI registers callbacks. A headless runner registers none or a logger.

## TUI Design

### Technology

Textual (by the same author as Rich, which is already a dependency). Cross-platform, keyboard-first, CSS-styled.

### Layout

Three-panel layout:

- **Left sidebar** — navigation and actions (kick off analyzers, settings). Collapsible.
- **Center panel** — context-dependent content (work queue, artifact details, agent output).
- **Bottom panel** — agent dashboard. Always visible when agents are running. Live-updating cards with agent name, progress, current tool, tokens, cost. Fades out when idle.

### Screens

1. **Home** — overview of recent runs, quick actions
2. **Analyzer** — pick targets (changed files, all files, specific paths), kick off analysis, watch agents in dashboard
3. **Queue** — browse completed artifacts. Drill into findings with syntax-highlighted code snippets, severity badges. Toggle findings on/off, dispatch fixers for selected items.
4. **Plan** — interactive planning. Chat-like interface with planner agent. Plan builds in side panel. Approve to save as artifact.
5. **Dashboard** — full-screen agent monitoring

### Visual Design

- Dark theme with severity-based color coding (red/high, yellow/medium, blue/low, dim/info)
- Syntax-highlighted code snippets in findings
- Smooth progress bars
- Status indicators: queued (dot), running (animated), done (check), failed (x)
- Keyboard-first with visible shortcuts
- Responsive across terminal sizes

## Package Structure

```
codemonkeys/
  __init__.py
  cli.py                        # entry point: restrict(cwd) → launch TUI

  core/
    __init__.py
    runner.py                   # AgentRunner
    sandbox.py                  # filesystem sandbox
    agents/
      __init__.py
      registry.py              # AgentSpec registry
      python_file_reviewer.py
      python_code_fixer.py
      changelog_reviewer.py
      readme_reviewer.py
      python_implementer.py
    prompts/
      __init__.py
      engineering_mindset.py
      python_guidelines.py
      code_quality.py
      security_observations.py
      python_cmd.py
      python_source_filter.py

  workflows/
    __init__.py
    engine.py                   # state machine runner, event emitter
    phases.py                   # phase types (automated, interactive, gate)
    review.py                   # review workflow definition
    implement.py                # implement workflow definition

  artifacts/
    __init__.py
    store.py                    # read/write/list artifacts in .codemonkeys/
    schemas/
      __init__.py
      findings.py              # FileFindings, Finding, FixRequest
      plans.py                 # FeaturePlan, BugFixPlan
      results.py               # FixResult, VerificationResult

  tui/
    __init__.py
    app.py                     # main Textual app
    theme.py                   # colors, styles
    screens/
      __init__.py
      home.py
      analyzer.py
      queue.py
      plan.py
      dashboard.py
    widgets/
      __init__.py
      agent_card.py            # live agent status card
      finding_view.py          # rendered finding with code snippet
      file_tree.py             # file browser
      progress.py              # progress bars and indicators
```

### Entry Point

```toml
[project.scripts]
codemonkeys = "codemonkeys.cli:main"
```

```python
def main():
    restrict(Path.cwd())
    app = CodemonkeysApp()
    app.run()
```

### Dependencies

- `claude-agent-sdk>=0.1.0` — agent execution
- `rich>=13.0` — terminal rendering (existing)
- `textual>=8.0` — TUI framework
- `pydantic>=2.0` — artifact schemas and structured output

## Existing Code

The following existing modules will be reorganized into the `core/` layer:

- `codemonkeys/runner.py` → `codemonkeys/core/runner.py`
- `codemonkeys/sandbox.py` → `codemonkeys/core/sandbox.py`
- `codemonkeys/agents/*.py` → `codemonkeys/core/agents/*.py`
- `codemonkeys/prompts/*.py` → `codemonkeys/core/prompts/*.py`

The `codemonkeys_reference/` directory will be archived — its coordinator pattern is superseded by the workflow engine, and its specialized agents (linter, type checker, test runner) are replaced by the mechanical checks phase in the review workflow.

## V1 Scope

Two workflows at launch:

1. **Code review** — analyze → triage → fix → verify
2. **Feature implementation** — plan → approve → implement → verify

The architecture supports adding more workflows (bug fix planning, test writing, dependency auditing) without modifying the engine or TUI framework.
