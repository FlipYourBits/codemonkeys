# Codemonkeys Dashboard — Design Spec

Web-based dashboard for running agents, viewing live output, and chaining results. Built on the existing core (`run_agent`, events, `AgentDefinition`) with zero changes to current code.

## Decisions

| Decision | Choice |
|---|---|
| Platform | Web (browser) |
| Backend | FastAPI + WebSocket |
| Frontend | Svelte (Vite) |
| File selection | Tree browser + git shortcuts + drag-and-drop |
| Agent chaining | Free-form (any output → any agent). No predefined workflows for now. |
| Live output | Expandable cards (compact by default, click to expand full event stream) |
| Results | Selectable findings with export. Fixer queue for batching fixes. |
| Agent config | Use defaults — no user overrides |
| Agent discovery | Registry via factory introspection (signatures + docstrings) |
| Concurrency | Max 3 agents running in parallel (hardcoded), excess queued |
| History | Session only — no persistence beyond JSONL logs on disk |
| Launch | Dev: separate backend/frontend. Prod: single `codemonkeys dashboard` command |

## UI Layout

Three-panel layout with a top bar.

### Top Bar

- Monkey emoji + "Codemonkeys" branding
- Project path indicator
- Session cost (sum of all runs)

### Left Panel — File Picker (280px)

- **Git shortcut buttons:** Changed, Staged, All .py (auto-populate the tree selection)
- **Search bar:** filter files by name
- **Project tree:** collapsible directory tree with checkboxes. Supports partial selection (select a directory = select all children).
- **Drag-and-drop zone:** drop files or folders to add them to selection
- **File count:** "N files selected" indicator

### Center Panel — Agent Monitor (flex)

**Launcher bar (top):**
- Agent dropdown (populated from registry)
- Run button
- Kill All button — cancels all running agents and clears the queue

**Agent cards (scrollable):**

Cards appear in sections: RUNNING, QUEUED, COMPLETED.

Compact card shows:
- **Status indicator:** pulsing dot (running), hollow circle (queued), checkmark (completed), X (error)
- **Agent name** and **model badge** (sonnet/haiku/opus)
- **Live token counter:** input/output tokens
- **Live cost:** dollar amount, updating in real time
- **Current tool call:** e.g. `Read(agents/fixer.py)` — shows what the agent is doing right now
- **Duration** (completed only)
- **Finding count** with "view" link (completed only)

Expanded card adds:
- Scrolling event log below the compact header
- Events are color-coded: TOOL (yellow), THINK (purple), TEXT (green), START (blue)
- Each event shows timestamp, type badge, and details (tool name + args, thinking text, etc.)
- Tool results shown as indented sub-entries
- Current tool call highlighted

**Click behavior:**
- Click a card → expands it AND updates the right panel to show that agent's results
- Click again → collapses, right panel shows all results unfiltered
- Click a different card → switches focus

### Right Panel — Results & Fixer Queue (320px)

**Tabbed view** with two tabs: Results and Fixer Queue.

**Results tab:**
- Header showing which agent's results are displayed
- For running agents: "streaming..." indicator, findings appear as they're detected
- For completed agents: full list of findings
- Each finding shows: checkbox, title, file:line, severity badge (color-coded), description
- Bottom bar: "Add to Queue (N)" button (for checked items), Export button

**Fixer Queue tab:**
- Status bar: item count + severity breakdown badges
- Items grouped by source agent
- Each item shows: checkbox, title, file:line, severity (color-coded left border), remove button (×)
- Items accumulate across multiple agent runs
- Bottom bar: "Fix Selected (N)" button, Select All, Clear Queue, Export JSON
- Clicking "Fix Selected" launches the fixer agent — it appears as a card in the center panel

### Fixer Queue Flow

1. **Collect:** run reviewers, browse findings in Results tab, check items
2. **Queue:** click "Add to Queue" — items move to the Fixer Queue tab with a badge count
3. **Review:** in Queue tab, select/deselect items, remove unwanted ones
4. **Fix:** click "Fix Selected" — fixer agent launches, appears as a running card in center panel

The queue is client-side (Svelte store). The backend only sees queue items when the user clicks Fix, at which point they're sent via `POST /api/runs`.

## Backend

### REST API

| Endpoint | Method | Purpose |
|---|---|---|
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/agents` | GET | List registered agents (name, description, accepted input types, output schema) |
| `/api/files/tree` | GET | Project file tree (uses `git ls-files` to respect .gitignore) |
| `/api/files/git/{mode}` | GET | Git-aware file lists: `changed`, `staged`, `all-py` |
| `/api/runs` | GET | List all runs in current session (for reconnection) |
| `/api/runs` | POST | Launch an agent run. Body: `{agent: str, input: {files?: str[], findings?: Finding[]}}`. Returns `{run_id: str}` immediately. |
| `/api/runs/{id}` | GET | Run status, result, and structured output |
| `/api/runs/{id}` | DELETE | Cancel a running agent |
| `/api/runs` | DELETE | Kill all — cancel all running agents and clear queue |

`POST /api/runs` is non-blocking — it creates an asyncio task and returns the `run_id`. Events stream over WebSocket.

### WebSocket

Single connection at `ws://localhost:{port}/ws`.

Server → client only. Multiplexes events from all running agents. Each message:

```json
{
  "run_id": "run_abc123",
  "event_type": "tool_call",
  "agent_name": "Python File Reviewer",
  "data": { ... },
  "timestamp": "2026-05-07T14:32:01.234Z"
}
```

Event types map directly to existing `codemonkeys.core.events`:
- `agent_started` — agent began running (includes model)
- `tool_call` — tool invoked (name + input)
- `tool_result` — tool returned (name + truncated output)
- `tool_denied` — tool blocked by allowlist
- `token_update` — cumulative token usage + cost
- `thinking_output` — Claude thinking block
- `text_output` — Claude text response
- `agent_completed` — run finished (includes RunResult summary)
- `agent_error` — run failed (error message)
- `rate_limit_hit` — rate limit encountered (wait time)

On WebSocket reconnect, the server sends a snapshot of all current run states so the UI can rebuild.

### Orchestrator

- Manages a pool of asyncio tasks, max 3 concurrent
- Excess runs go to a FIFO queue with "queued" status
- When a running agent completes (or is cancelled), the next queued run starts
- Each run gets a unique ID (e.g., `run_{uuid4().hex[:8]}`)
- Event callback: serializes each event from `run_agent()` → pushes to WebSocket hub
- Holds `RunResult` objects in memory (dict keyed by run_id)
- Kill All: cancels all asyncio tasks + clears the queue

### Agent Registry

No new data structures. The registry introspects existing factory functions at import time:

- **Name:** factory function name (e.g., `python_file_reviewer`)
- **Description:** factory docstring
- **Accepts:** inferred from function signature parameter types (`files: list[str]` → files, `findings: list[Finding]` → findings)
- **Produces:** inferred from the `output_schema` on the `AgentDefinition` returned by the factory
- **Model:** default argument value from signature

The registry scans `codemonkeys.agents` on startup, collects all public factory functions, and exposes them via `GET /api/agents`.

Adding a new agent: write the factory with a docstring. It appears in the dashboard automatically.

For chaining: the dashboard matches `produces` of one agent to `accepts` of another. Compatible agents are highlighted when selecting an output as input.

## Frontend

### Tech Stack

- Svelte with Vite
- No component library — custom components matching the mockup aesthetic
- Dark theme

### Svelte Stores

| Store | Type | Updated by |
|---|---|---|
| `agentRuns` | `Map<string, RunState>` | WebSocket events |
| `selectedRun` | `string \| null` (run_id) | User click on card |
| `fixerQueue` | `Finding[]` | User selection in Results tab |
| `fileSelection` | `string[]` | File picker interactions |
| `agents` | `AgentMeta[]` | `GET /api/agents` on startup |

`RunState` contains: run_id, agent name, model, status (running/queued/completed/error), token counts, cost, current tool, events array, result (when completed).

### WebSocket Connection

- Single connection opened on page load
- Auto-reconnect with exponential backoff
- On reconnect: `GET /api/runs` to rebuild state
- Each incoming message updates the `agentRuns` store by `run_id`
- Svelte reactivity handles all re-renders

### Components

| Component | Responsibility |
|---|---|
| `FileTree` | Recursive directory tree with checkboxes, expand/collapse |
| `GitButtons` | Changed/Staged/All .py shortcut buttons |
| `DropZone` | Drag-and-drop file addition |
| `AgentLauncher` | Agent dropdown, Run button, Kill All |
| `AgentCard` | Compact/expanded card with all status states |
| `EventLog` | Scrolling event stream inside expanded card |
| `FindingsList` | Selectable findings with severity badges |
| `FixerQueue` | Queue management with batch actions |
| `TopBar` | Branding, project path, session cost |

## Project Structure

```
codemonkeys/
  agents/                      # existing — unchanged
  core/                        # existing — unchanged
  display/                     # existing — unchanged
  dashboard/
    __init__.py
    server.py                  # FastAPI app, routes, WebSocket endpoint
    orchestrator.py            # concurrent run management, event routing
    registry.py                # agent introspection + metadata
    static/                    # built Svelte output (git-ignored, built on demand)
frontend/
  src/
    lib/
      stores/                  # ws.ts, runs.ts, queue.ts, files.ts
      components/              # all Svelte components
    routes/
      +page.svelte             # single-page dashboard
    app.html
  package.json
  vite.config.js
  svelte.config.js
```

- `dashboard/` is a new package — no changes to existing code
- `frontend/` at repo root (separate build target)
- `dashboard/static/` is git-ignored, built from `frontend/` on demand
- Three new Python files on the backend

## Launch

**Development:**
```bash
# Terminal 1: backend
uvicorn codemonkeys.dashboard.server:app --reload --port 8000

# Terminal 2: frontend with API proxy
cd frontend && npm run dev -- --port 5173
```

Vite proxies `/api` and `/ws` to the backend during development for hot reload.

**Production:**
```bash
codemonkeys dashboard --port 8000
```

Builds the Svelte app if needed (or uses cached build in `dashboard/static/`), then starts FastAPI serving static files + API. No Node.js required at runtime.
