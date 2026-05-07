# Codemonkeys Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web dashboard (FastAPI + Svelte) for running codemonkeys agents, viewing live output, and chaining results through a fixer queue.

**Architecture:** FastAPI backend serves a REST API and WebSocket endpoint. An orchestrator manages concurrent agent runs (max 3), piping events from `run_agent()` through the WebSocket to a Svelte frontend. The agent registry auto-discovers factory functions via introspection. The Svelte frontend has three panels: file picker, agent monitor with expandable cards, and a results/fixer-queue panel.

**Tech Stack:** Python 3.10+ / FastAPI / uvicorn / WebSocket, Svelte 5 / Vite / TypeScript

**Spec:** `docs/specs/2026-05-07-dashboard-design.md`

---

## File Map

### Backend (Python)

| File | Responsibility |
|---|---|
| `codemonkeys/dashboard/__init__.py` | Package init, exports `app` |
| `codemonkeys/dashboard/registry.py` | Scans `codemonkeys.agents`, introspects factories, exposes metadata |
| `codemonkeys/dashboard/orchestrator.py` | Manages concurrent runs (max 3), queues excess, routes events to WebSocket hub |
| `codemonkeys/dashboard/server.py` | FastAPI app: REST routes, WebSocket endpoint, static file serving, CLI entry |
| `tests/test_registry.py` | Tests for agent registry introspection |
| `tests/test_orchestrator.py` | Tests for orchestrator concurrency, queueing, cancellation |
| `tests/test_server.py` | Tests for REST endpoints and WebSocket |

### Frontend (Svelte/TypeScript)

| File | Responsibility |
|---|---|
| `frontend/package.json` | Dependencies: svelte, vite, typescript |
| `frontend/vite.config.ts` | Vite config with API/WS proxy for dev |
| `frontend/svelte.config.js` | Svelte compiler config |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/src/app.html` | HTML shell |
| `frontend/src/app.css` | Global dark theme styles |
| `frontend/src/routes/+page.svelte` | Root page — three-panel layout |
| `frontend/src/lib/types.ts` | Shared TypeScript types (RunState, Finding, AgentMeta, etc.) |
| `frontend/src/lib/stores/ws.ts` | WebSocket connection with auto-reconnect |
| `frontend/src/lib/stores/runs.ts` | Agent runs store — updated by WebSocket events |
| `frontend/src/lib/stores/files.ts` | File selection store |
| `frontend/src/lib/stores/queue.ts` | Fixer queue store |
| `frontend/src/lib/stores/agents.ts` | Agent registry store (fetched on load) |
| `frontend/src/lib/components/TopBar.svelte` | Branding, project path, session cost |
| `frontend/src/lib/components/FileTree.svelte` | Recursive directory tree with checkboxes |
| `frontend/src/lib/components/GitButtons.svelte` | Changed/Staged/All .py shortcut buttons |
| `frontend/src/lib/components/DropZone.svelte` | Drag-and-drop file addition |
| `frontend/src/lib/components/FilePicker.svelte` | Composes FileTree + GitButtons + DropZone + search |
| `frontend/src/lib/components/AgentLauncher.svelte` | Agent dropdown, Run button, Kill All |
| `frontend/src/lib/components/AgentCard.svelte` | Compact/expanded card with all status states |
| `frontend/src/lib/components/EventLog.svelte` | Scrolling event stream inside expanded card |
| `frontend/src/lib/components/AgentMonitor.svelte` | Composes AgentLauncher + scrollable AgentCards |
| `frontend/src/lib/components/FindingsList.svelte` | Selectable findings with severity badges |
| `frontend/src/lib/components/FixerQueue.svelte` | Queue management with batch actions |
| `frontend/src/lib/components/ResultsPanel.svelte` | Tabbed Results + Fixer Queue |

---

## Task 1: Add docstrings to existing agent factories

The registry will introspect factory docstrings. The existing factories need one-line docstrings that describe what the agent does.

**Files:**
- Modify: `codemonkeys/agents/python_file_reviewer.py:24-29`
- Modify: `codemonkeys/agents/fixer.py:30-35`
- Modify: `codemonkeys/agents/review_auditor.py` (the `make_review_auditor` function)

- [ ] **Step 1: Add docstring to `make_python_file_reviewer`**

```python
def make_python_file_reviewer(
    files: list[str],
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Reviews Python files for code quality and security issues."""
    file_list = "\n".join(f"- `{f}`" for f in files)
```

- [ ] **Step 2: Add docstring to `make_fixer`**

```python
def make_fixer(
    items: list[FixItem],
    *,
    model: str = "opus",
) -> AgentDefinition:
    """Applies fixes from structured findings to the codebase."""
    findings_text = ""
```

- [ ] **Step 3: Add docstring to `make_review_auditor`**

Find the `make_review_auditor` function and add:

```python
    """Audits a reviewer agent's work to verify behavior compliance."""
```

- [ ] **Step 4: Run tests to confirm nothing broke**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/ -v`
Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add codemonkeys/agents/python_file_reviewer.py codemonkeys/agents/fixer.py codemonkeys/agents/review_auditor.py
git commit -m "docs: add docstrings to agent factories for dashboard registry"
```

---

## Task 2: Agent Registry

Scans `codemonkeys.agents` and builds metadata from factory function introspection.

**Files:**
- Create: `codemonkeys/dashboard/__init__.py`
- Create: `codemonkeys/dashboard/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Create the dashboard package**

Create `codemonkeys/dashboard/__init__.py`:

```python
"""Codemonkeys web dashboard."""
```

- [ ] **Step 2: Write the failing test for registry discovery**

Create `tests/test_registry.py`:

```python
from codemonkeys.dashboard.registry import AgentMeta, discover_agents


def test_discover_finds_existing_agents():
    agents = discover_agents()
    names = [a.name for a in agents]
    assert "make_python_file_reviewer" in names
    assert "make_fixer" in names
    assert "make_review_auditor" in names


def test_agent_meta_has_description():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert "Python files" in reviewer.description


def test_agent_meta_has_accepts():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert reviewer.accepts == ["files"]
    fixer = next(a for a in agents if a.name == "make_fixer")
    assert reviewer.accepts != fixer.accepts


def test_agent_meta_has_default_model():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert reviewer.default_model == "sonnet"
    fixer = next(a for a in agents if a.name == "make_fixer")
    assert fixer.default_model == "opus"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.dashboard.registry'`

- [ ] **Step 4: Implement the registry**

Create `codemonkeys/dashboard/registry.py`:

```python
"""Agent registry — discovers agent factories via introspection."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field

import codemonkeys.agents as agents_pkg
from codemonkeys.core.types import AgentDefinition


@dataclass(frozen=True)
class AgentMeta:
    """Metadata about a registered agent factory."""

    name: str
    description: str
    accepts: list[str] = field(default_factory=list)
    default_model: str = "sonnet"
    produces: str | None = None


def _infer_accepts(sig: inspect.Signature) -> list[str]:
    """Infer input type from the first parameter's type annotation."""
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "model"):
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            return ["unknown"]
        ann_str = str(annotation)
        if "str" in ann_str and "list" in ann_str.lower():
            return ["files"]
        if "FixItem" in ann_str:
            return ["findings"]
        if "RunResult" in ann_str:
            return ["run_result"]
        return ["unknown"]
    return ["unknown"]


def _infer_produces(func: object) -> str | None:
    """Infer output type from calling the function's return type's output_schema."""
    sig = inspect.signature(func)  # type: ignore[arg-type]
    ret = sig.return_annotation
    if ret is AgentDefinition or (isinstance(ret, type) and issubclass(ret, AgentDefinition)):
        return None
    return None


def discover_agents() -> list[AgentMeta]:
    """Scan codemonkeys.agents and return metadata for all factory functions."""
    agents: list[AgentMeta] = []

    for module_info in pkgutil.iter_modules(agents_pkg.__path__):
        module = importlib.import_module(f"codemonkeys.agents.{module_info.name}")

        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name)
            if not callable(obj) or inspect.isclass(obj):
                continue

            sig = inspect.signature(obj)
            if sig.return_annotation not in (AgentDefinition, "AgentDefinition"):
                ret_str = str(sig.return_annotation)
                if "AgentDefinition" not in ret_str:
                    continue

            description = (inspect.getdoc(obj) or "").split("\n")[0]
            accepts = _infer_accepts(sig)

            default_model = "sonnet"
            if "model" in sig.parameters:
                model_param = sig.parameters["model"]
                if model_param.default is not inspect.Parameter.empty:
                    default_model = model_param.default

            agents.append(
                AgentMeta(
                    name=attr_name,
                    description=description,
                    accepts=accepts,
                    default_model=default_model,
                )
            )

    return sorted(agents, key=lambda a: a.name)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_registry.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Run linting**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/dashboard/__init__.py codemonkeys/dashboard/registry.py tests/test_registry.py
git commit -m "feat(dashboard): add agent registry with factory introspection"
```

---

## Task 3: Orchestrator

Manages concurrent agent runs with a max-3 pool, FIFO queue, event routing, and cancellation.

**Files:**
- Create: `codemonkeys/dashboard/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test for basic run management**

Create `tests/test_orchestrator.py`:

```python
import asyncio

import pytest
from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage
from codemonkeys.dashboard.orchestrator import Orchestrator


class _DummyOutput(BaseModel):
    message: str


def _make_agent(name: str = "test_agent") -> AgentDefinition:
    return AgentDefinition(
        name=name,
        model="sonnet",
        system_prompt="You are a test agent.",
        tools=["Read"],
    )


@pytest.fixture
def orchestrator():
    return Orchestrator(max_concurrent=2)


async def test_submit_returns_run_id(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    run_id = await orchestrator.submit(_make_agent(), "test prompt")
    assert run_id.startswith("run_")


async def test_get_run_returns_state(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    run_id = await orchestrator.submit(_make_agent(), "test prompt")
    await asyncio.sleep(0.1)
    state = orchestrator.get_run(run_id)
    assert state is not None
    assert state["status"] in ("running", "completed")


async def test_list_runs(orchestrator: Orchestrator):
    async def fake_runner(agent, prompt, on_event=None):
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = fake_runner
    await orchestrator.submit(_make_agent("a"), "prompt")
    await orchestrator.submit(_make_agent("b"), "prompt")
    runs = orchestrator.list_runs()
    assert len(runs) == 2


async def test_max_concurrent_queues_excess(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner

    id1 = await orchestrator.submit(_make_agent("a"), "prompt")
    id2 = await orchestrator.submit(_make_agent("b"), "prompt")
    id3 = await orchestrator.submit(_make_agent("c"), "prompt")

    await asyncio.sleep(0.05)

    states = {rid: orchestrator.get_run(rid)["status"] for rid in [id1, id2, id3]}
    assert states[id3] == "queued"
    assert list(states.values()).count("running") == 2

    gate.set()
    await asyncio.sleep(0.1)

    assert orchestrator.get_run(id3)["status"] == "completed"


async def test_cancel_running(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner
    run_id = await orchestrator.submit(_make_agent(), "prompt")
    await asyncio.sleep(0.05)

    cancelled = orchestrator.cancel(run_id)
    assert cancelled is True
    assert orchestrator.get_run(run_id)["status"] == "cancelled"
    gate.set()


async def test_kill_all(orchestrator: Orchestrator):
    gate = asyncio.Event()

    async def slow_runner(agent, prompt, on_event=None):
        await gate.wait()
        return RunResult(
            output=None, text="done", usage=TokenUsage(input_tokens=0, output_tokens=0),
            cost_usd=0.0, duration_ms=100, agent_def=agent,
        )

    orchestrator._run_agent_fn = slow_runner
    await orchestrator.submit(_make_agent("a"), "prompt")
    await orchestrator.submit(_make_agent("b"), "prompt")
    await orchestrator.submit(_make_agent("c"), "prompt")
    await asyncio.sleep(0.05)

    orchestrator.kill_all()
    await asyncio.sleep(0.05)

    for run in orchestrator.list_runs():
        assert run["status"] in ("cancelled",)
    gate.set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the orchestrator**

Create `codemonkeys/dashboard/orchestrator.py`:

```python
"""Agent orchestrator — manages concurrent runs with a bounded pool."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict
from typing import Any, Callable, Awaitable

from codemonkeys.core.events import Event, EventHandler
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import AgentDefinition, RunResult


RunAgentFn = Callable[..., Awaitable[RunResult]]


class Orchestrator:
    """Manages concurrent agent runs with a max-concurrency pool."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._max_concurrent = max_concurrent
        self._runs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._queue: list[tuple[str, AgentDefinition, str]] = []
        self._run_agent_fn: RunAgentFn = run_agent
        self._event_listeners: list[Callable[[str, dict], None]] = []
        self._active_count = 0

    def add_event_listener(self, listener: Callable[[str, dict], None]) -> None:
        self._event_listeners.append(listener)

    def _emit_ws_event(self, run_id: str, event: Event) -> None:
        event_data = {
            "run_id": run_id,
            "event_type": type(event).__name__,
            "agent_name": event.agent_name,
            "data": asdict(event),
            "timestamp": event.timestamp,
        }
        for listener in self._event_listeners:
            listener(run_id, event_data)

    async def submit(self, agent: AgentDefinition, prompt: str) -> str:
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        self._runs[run_id] = {
            "run_id": run_id,
            "agent_name": agent.name,
            "model": agent.model,
            "status": "queued",
            "cost_usd": 0.0,
            "tokens": {"input": 0, "output": 0},
            "current_tool": None,
            "events": [],
            "result": None,
            "started_at": None,
            "completed_at": None,
        }

        if self._active_count < self._max_concurrent:
            self._start_run(run_id, agent, prompt)
        else:
            self._queue.append((run_id, agent, prompt))

        return run_id

    def _start_run(self, run_id: str, agent: AgentDefinition, prompt: str) -> None:
        self._active_count += 1
        self._runs[run_id]["status"] = "running"
        self._runs[run_id]["started_at"] = time.time()

        def on_event(event: Event) -> None:
            self._emit_ws_event(run_id, event)

        task = asyncio.create_task(self._execute(run_id, agent, prompt, on_event))
        self._tasks[run_id] = task

    async def _execute(
        self,
        run_id: str,
        agent: AgentDefinition,
        prompt: str,
        on_event: EventHandler,
    ) -> None:
        try:
            result = await self._run_agent_fn(agent, prompt, on_event=on_event)
            if self._runs[run_id]["status"] == "cancelled":
                return
            self._runs[run_id]["status"] = "completed" if not result.error else "error"
            self._runs[run_id]["result"] = result
            self._runs[run_id]["cost_usd"] = result.cost_usd
            self._runs[run_id]["tokens"] = {
                "input": result.usage.input_tokens,
                "output": result.usage.output_tokens,
            }
            self._runs[run_id]["completed_at"] = time.time()
        except asyncio.CancelledError:
            self._runs[run_id]["status"] = "cancelled"
        except Exception as exc:
            self._runs[run_id]["status"] = "error"
            self._runs[run_id]["result"] = str(exc)
            self._runs[run_id]["completed_at"] = time.time()
        finally:
            self._active_count -= 1
            self._tasks.pop(run_id, None)
            self._drain_queue()

    def _drain_queue(self) -> None:
        while self._queue and self._active_count < self._max_concurrent:
            run_id, agent, prompt = self._queue.pop(0)
            if self._runs[run_id]["status"] == "cancelled":
                continue
            self._start_run(run_id, agent, prompt)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return list(self._runs.values())

    def cancel(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if state is None:
            return False
        if state["status"] == "queued":
            state["status"] = "cancelled"
            self._queue = [(rid, a, p) for rid, a, p in self._queue if rid != run_id]
            return True
        if state["status"] == "running":
            task = self._tasks.get(run_id)
            if task:
                task.cancel()
            state["status"] = "cancelled"
            return True
        return False

    def kill_all(self) -> None:
        for run_id, agent, prompt in self._queue:
            self._runs[run_id]["status"] = "cancelled"
        self._queue.clear()
        for run_id, task in list(self._tasks.items()):
            task.cancel()
            self._runs[run_id]["status"] = "cancelled"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_orchestrator.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run linting**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/dashboard/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(dashboard): add orchestrator with concurrency pool and cancellation"
```

---

## Task 4: FastAPI Server — REST Endpoints

The HTTP server with all REST routes. WebSocket comes in Task 5.

**Files:**
- Create: `codemonkeys/dashboard/server.py`
- Create: `tests/test_server.py`
- Modify: `pyproject.toml` (add fastapi, uvicorn dependencies)

- [ ] **Step 1: Add FastAPI dependencies to pyproject.toml**

Add `fastapi` and `uvicorn` to the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "claude-agent-sdk>=0.1.0,<1.0",
    "rich>=14.2.0",
    "textual>=8.0",
    "pydantic>=2.0,<3",
    "landlock>=1.0.0.dev5; sys_platform == 'linux'",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
]
```

- [ ] **Step 2: Install new dependencies**

Run: `cd /home/jwhiteley/git/codemonkeys && uv sync`

- [ ] **Step 3: Write failing tests for REST endpoints**

Create `tests/test_server.py`:

```python
import pytest
from fastapi.testclient import TestClient

from codemonkeys.dashboard.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_agents(client: TestClient):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    names = [a["name"] for a in data]
    assert "make_python_file_reviewer" in names


def test_get_agents_has_fields(client: TestClient):
    resp = client.get("/api/agents")
    agent = resp.json()[0]
    assert "name" in agent
    assert "description" in agent
    assert "accepts" in agent
    assert "default_model" in agent


def test_get_files_tree(client: TestClient):
    resp = client.get("/api/files/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(f.endswith(".py") for f in data)


def test_get_files_git_changed(client: TestClient):
    resp = client.get("/api/files/git/changed")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_files_git_staged(client: TestClient):
    resp = client.get("/api/files/git/staged")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_files_git_all_py(client: TestClient):
    resp = client.get("/api/files/git/all-py")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert all(f.endswith(".py") for f in data)


def test_get_files_git_invalid_mode(client: TestClient):
    resp = client.get("/api/files/git/invalid")
    assert resp.status_code == 400


def test_list_runs_empty(client: TestClient):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_server.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 5: Implement the server**

Create `codemonkeys/dashboard/server.py`:

```python
"""FastAPI server — REST endpoints, WebSocket hub, static file serving."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from codemonkeys.dashboard.orchestrator import Orchestrator
from codemonkeys.dashboard.registry import discover_agents


STATIC_DIR = Path(__file__).parent / "static"


def _git_files_changed() -> list[str]:
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True, text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True, text=True,
    )
    all_files = set(unstaged.stdout.strip().splitlines() + staged.stdout.strip().splitlines())
    return sorted(f for f in all_files if f and Path(f).exists())


def _git_files_staged() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True, text=True,
    )
    return sorted(f for f in result.stdout.strip().splitlines() if f and Path(f).exists())


def _git_files_all_py() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py", "--cached"],
        capture_output=True, text=True,
    )
    return sorted(f for f in result.stdout.strip().splitlines() if f and Path(f).exists())


def _file_tree() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True, text=True,
    )
    return sorted(f for f in result.stdout.strip().splitlines() if f)


def create_app() -> FastAPI:
    app = FastAPI(title="Codemonkeys Dashboard")
    orchestrator = Orchestrator(max_concurrent=3)
    agents = discover_agents()
    app.state.orchestrator = orchestrator

    @app.get("/api/agents")
    def get_agents():
        return [
            {
                "name": a.name,
                "description": a.description,
                "accepts": a.accepts,
                "default_model": a.default_model,
            }
            for a in agents
        ]

    @app.get("/api/files/tree")
    def get_files_tree():
        return _file_tree()

    @app.get("/api/files/git/{mode}")
    def get_files_git(mode: str):
        if mode == "changed":
            return _git_files_changed()
        elif mode == "staged":
            return _git_files_staged()
        elif mode == "all-py":
            return _git_files_all_py()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    @app.get("/api/runs")
    def list_runs():
        return orchestrator.list_runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        state = orchestrator.get_run(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return state

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_server.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 7: Run linting**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml codemonkeys/dashboard/server.py tests/test_server.py
git commit -m "feat(dashboard): add FastAPI server with REST endpoints"
```

---

## Task 5: FastAPI Server — WebSocket + Run Submission

Add the WebSocket endpoint for event streaming and the POST /api/runs endpoint that launches agents.

**Files:**
- Modify: `codemonkeys/dashboard/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for WebSocket and run submission**

Add to `tests/test_server.py`:

```python
import asyncio
import json


def test_post_run_missing_agent(client: TestClient):
    resp = client.post("/api/runs", json={"agent": "nonexistent", "input": {"files": ["foo.py"]}})
    assert resp.status_code == 404


def test_post_run_returns_run_id(client: TestClient):
    resp = client.post("/api/runs", json={
        "agent": "make_python_file_reviewer",
        "input": {"files": ["codemonkeys/__init__.py"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["run_id"].startswith("run_")


def test_delete_runs_kill_all(client: TestClient):
    resp = client.delete("/api/runs")
    assert resp.status_code == 200


def test_websocket_connects(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        pass


def test_delete_run_not_found(client: TestClient):
    resp = client.delete("/api/runs/run_nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify new ones fail**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_server.py -v`
Expected: New tests FAIL (404 for POST /api/runs, no WebSocket endpoint)

- [ ] **Step 3: Add WebSocket, POST /api/runs, DELETE endpoints to server.py**

Add these imports to the top of `codemonkeys/dashboard/server.py`:

```python
import asyncio
import json
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel as PydanticBaseModel
```

Add a request model and the WebSocket hub inside `create_app()`, after the orchestrator setup:

```python
    # WebSocket connections
    ws_connections: list[WebSocket] = []

    def broadcast_event(run_id: str, event_data: dict):
        """Queue event for all connected WebSocket clients."""
        msg = json.dumps(event_data, default=str)
        disconnected = []
        for ws in ws_connections:
            try:
                asyncio.create_task(ws.send_text(msg))
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            ws_connections.remove(ws)

    orchestrator.add_event_listener(broadcast_event)
```

Add these route handlers inside `create_app()`:

```python
    @app.post("/api/runs")
    async def submit_run(body: dict):
        agent_name = body.get("agent")
        input_data = body.get("input", {})

        agent_meta = next((a for a in agents if a.name == agent_name), None)
        if agent_meta is None:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")

        # Import the factory and build the agent definition
        from codemonkeys.dashboard.registry import get_factory
        factory = get_factory(agent_name)
        if factory is None:
            raise HTTPException(status_code=404, detail=f"Factory not found: {agent_name}")

        files = input_data.get("files", [])
        findings = input_data.get("findings")

        if findings is not None:
            from codemonkeys.agents.fixer import FixItem
            items = [FixItem(**f) for f in findings]
            agent_def = factory(items)
        else:
            agent_def = factory(files)

        prompt = "Execute your task on the provided inputs."
        run_id = await orchestrator.submit(agent_def, prompt)
        return {"run_id": run_id}

    @app.delete("/api/runs/{run_id}")
    def cancel_run(run_id: str):
        success = orchestrator.cancel(run_id)
        if not success:
            raise HTTPException(status_code=404, detail="Run not found or not cancellable")
        return {"status": "cancelled"}

    @app.delete("/api/runs")
    def kill_all_runs():
        orchestrator.kill_all()
        return {"status": "killed"}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_connections.append(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_connections.remove(ws)
```

Add a `get_factory` function to `codemonkeys/dashboard/registry.py`:

```python
def get_factory(name: str) -> Callable | None:
    """Get an agent factory function by name."""
    for module_info in pkgutil.iter_modules(agents_pkg.__path__):
        module = importlib.import_module(f"codemonkeys.agents.{module_info.name}")
        obj = getattr(module, name, None)
        if obj is not None and callable(obj):
            return obj
    return None
```

Add the `Callable` import to registry.py's imports:

```python
from typing import Callable
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/test_server.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 5: Run linting**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run ruff check --fix . && uv run ruff format .`

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/dashboard/server.py codemonkeys/dashboard/registry.py tests/test_server.py
git commit -m "feat(dashboard): add WebSocket hub, run submission, and cancellation endpoints"
```

---

## Task 6: CLI Entry Point

Add `codemonkeys dashboard` command that starts the server.

**Files:**
- Modify: `codemonkeys/dashboard/server.py` (add `main()`)
- Modify: `pyproject.toml` (add CLI entry point)

- [ ] **Step 1: Add main() to server.py**

Add at the bottom of `codemonkeys/dashboard/server.py`:

```python
def main() -> None:
    """CLI entry point for `codemonkeys dashboard`."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Start the Codemonkeys dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    args = parser.parse_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)
```

- [ ] **Step 2: Add CLI entry point to pyproject.toml**

Update the `[project.scripts]` section:

```toml
[project.scripts]
codemonkeys = "codemonkeys.run_review:main"
codemonkeys-dashboard = "codemonkeys.dashboard.server:main"
```

- [ ] **Step 3: Install and verify the CLI**

Run: `cd /home/jwhiteley/git/codemonkeys && uv sync && uv run codemonkeys-dashboard --help`
Expected: Prints help text showing `--port` and `--host` options.

- [ ] **Step 4: Commit**

```bash
git add codemonkeys/dashboard/server.py pyproject.toml
git commit -m "feat(dashboard): add codemonkeys-dashboard CLI entry point"
```

---

## Task 7: Svelte Project Scaffold

Set up the frontend build toolchain with Vite, Svelte 5, TypeScript, and API proxy.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/svelte.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/app.html`
- Create: `frontend/src/app.css`
- Create: `frontend/src/routes/+page.svelte`
- Modify: `.gitignore` (add frontend/node_modules, dashboard/static)

- [ ] **Step 1: Initialize the Svelte project**

Run:
```bash
cd /home/jwhiteley/git/codemonkeys
mkdir -p frontend
cd frontend
npm create svelte@latest . -- --template skeleton --types typescript --no-add-ons --no-install
npm install
```

If the interactive create-svelte prompt doesn't support all those flags, create the files manually:

Create `frontend/package.json`:

```json
{
  "name": "codemonkeys-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "svelte": "^5.0.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.0.0",
    "vite": "^6.0.0"
  }
}
```

Then run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm install`

- [ ] **Step 2: Create vite.config.ts with API proxy**

Create `frontend/vite.config.ts`:

```typescript
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
```

- [ ] **Step 3: Create svelte.config.js**

Create `frontend/svelte.config.js`:

```javascript
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: '../codemonkeys/dashboard/static',
      assets: '../codemonkeys/dashboard/static',
      fallback: 'index.html',
    }),
  },
};
```

- [ ] **Step 4: Create tsconfig.json**

Create `frontend/tsconfig.json`:

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  }
}
```

- [ ] **Step 5: Create app.html shell**

Create `frontend/src/app.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Codemonkeys Dashboard</title>
    %sveltekit.head%
  </head>
  <body data-sveltekit-prerender="true">
    %sveltekit.body%
  </body>
</html>
```

- [ ] **Step 6: Create global CSS with dark theme**

Create `frontend/src/app.css`:

```css
:root {
  --bg: #0f0f1a;
  --bg-raised: #1a1a2e;
  --bg-hover: #222240;
  --border: #2a2a4a;
  --text: #e0e0e0;
  --text-dim: #888;
  --accent: #818cf8;
  --green: #4ade80;
  --red: #ef4444;
  --yellow: #fbbf24;
  --orange: #f97316;
  --blue: #60a5fa;
  --purple: #c084fc;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

button {
  cursor: pointer;
  font-family: inherit;
}

code, pre {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
```

- [ ] **Step 7: Create placeholder root page**

Create `frontend/src/routes/+page.svelte`:

```svelte
<script lang="ts">
  import '../app.css';
</script>

<div class="dashboard">
  <header class="topbar">
    <div class="brand">
      <span class="logo">🐒</span>
      <span class="title">Codemonkeys</span>
    </div>
    <div class="session-cost">
      <span class="label">Session cost:</span>
      <span class="value">$0.00</span>
    </div>
  </header>
  <main class="panels">
    <aside class="file-picker">File Picker (TODO)</aside>
    <section class="agent-monitor">Agent Monitor (TODO)</section>
    <aside class="results-panel">Results Panel (TODO)</aside>
  </main>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 2px solid var(--border);
    background: var(--bg-raised);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo { font-size: 18px; }
  .title { font-weight: 700; font-size: 16px; }

  .session-cost .label {
    font-size: 12px;
    color: var(--text-dim);
    margin-right: 8px;
  }

  .session-cost .value {
    font-size: 14px;
    font-weight: 600;
    color: var(--green);
  }

  .panels {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    flex: 1;
    overflow: hidden;
  }

  .file-picker {
    border-right: 1px solid var(--border);
    padding: 16px;
    overflow-y: auto;
  }

  .agent-monitor {
    overflow-y: auto;
    padding: 16px;
  }

  .results-panel {
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
  }
</style>
```

- [ ] **Step 8: Update .gitignore**

Add to `.gitignore`:

```
frontend/node_modules/
frontend/.svelte-kit/
codemonkeys/dashboard/static/
.superpowers/
```

- [ ] **Step 9: Verify the frontend builds**

Run:
```bash
cd /home/jwhiteley/git/codemonkeys/frontend
npm run build
```
Expected: Build succeeds, output goes to `codemonkeys/dashboard/static/`.

- [ ] **Step 10: Verify dev server starts**

Run:
```bash
cd /home/jwhiteley/git/codemonkeys/frontend
npm run dev -- --port 5173
```
Expected: Vite dev server starts on port 5173. Kill it after confirming.

- [ ] **Step 11: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat(dashboard): scaffold Svelte frontend with SvelteKit, dark theme, and three-panel layout"
```

---

## Task 8: TypeScript Types and Svelte Stores

Shared types and reactive stores for WebSocket, agent runs, file selection, and fixer queue.

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/stores/ws.ts`
- Create: `frontend/src/lib/stores/runs.ts`
- Create: `frontend/src/lib/stores/files.ts`
- Create: `frontend/src/lib/stores/queue.ts`
- Create: `frontend/src/lib/stores/agents.ts`

- [ ] **Step 1: Create shared types**

Create `frontend/src/lib/types.ts`:

```typescript
export type RunStatus = 'queued' | 'running' | 'completed' | 'error' | 'cancelled';
export type Severity = 'high' | 'medium' | 'low' | 'info';

export interface AgentMeta {
  name: string;
  description: string;
  accepts: string[];
  default_model: string;
}

export interface TokenUsage {
  input: number;
  output: number;
}

export interface RunState {
  run_id: string;
  agent_name: string;
  model: string;
  status: RunStatus;
  cost_usd: number;
  tokens: TokenUsage;
  current_tool: string | null;
  events: AgentEvent[];
  result: unknown | null;
  started_at: number | null;
  completed_at: number | null;
}

export interface AgentEvent {
  run_id: string;
  event_type: string;
  agent_name: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface Finding {
  file: string;
  line: number | null;
  severity: Severity;
  category: string;
  title: string;
  description: string;
  suggestion: string | null;
}

export interface QueueItem extends Finding {
  source_agent: string;
  source_run_id: string;
  selected: boolean;
}

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[];
  selected: boolean;
  expanded: boolean;
}
```

- [ ] **Step 2: Create WebSocket store**

Create `frontend/src/lib/stores/ws.ts`:

```typescript
import { writable } from 'svelte/store';
import type { AgentEvent } from '$lib/types';

export const connected = writable(false);
export const lastEvent = writable<AgentEvent | null>(null);

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;

export function connect() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws`;

  socket = new WebSocket(url);

  socket.onopen = () => {
    connected.set(true);
    reconnectDelay = 1000;
  };

  socket.onmessage = (event) => {
    const data: AgentEvent = JSON.parse(event.data);
    lastEvent.set(data);
  };

  socket.onclose = () => {
    connected.set(false);
    socket = null;
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      connect();
    }, reconnectDelay);
  };

  socket.onerror = () => {
    socket?.close();
  };
}

export function disconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  socket?.close();
  socket = null;
}
```

- [ ] **Step 3: Create agent runs store**

Create `frontend/src/lib/stores/runs.ts`:

```typescript
import { writable, derived } from 'svelte/store';
import type { RunState, AgentEvent } from '$lib/types';
import { lastEvent } from './ws';

export const runs = writable<Map<string, RunState>>(new Map());
export const selectedRunId = writable<string | null>(null);

export const selectedRun = derived(
  [runs, selectedRunId],
  ([$runs, $selectedRunId]) => $selectedRunId ? $runs.get($selectedRunId) ?? null : null,
);

export const sessionCost = derived(runs, ($runs) => {
  let total = 0;
  for (const run of $runs.values()) {
    total += run.cost_usd;
  }
  return total;
});

export const runsByStatus = derived(runs, ($runs) => {
  const running: RunState[] = [];
  const queued: RunState[] = [];
  const completed: RunState[] = [];

  for (const run of $runs.values()) {
    if (run.status === 'running') running.push(run);
    else if (run.status === 'queued') queued.push(run);
    else completed.push(run);
  }

  return { running, queued, completed };
});

lastEvent.subscribe((event) => {
  if (!event) return;

  runs.update(($runs) => {
    const run = $runs.get(event.run_id);
    if (!run) return $runs;

    run.events.push(event);

    if (event.event_type === 'TokenUpdate') {
      const data = event.data as Record<string, unknown>;
      const usage = data.usage as Record<string, number> | undefined;
      if (usage) {
        run.tokens = { input: usage.input_tokens ?? 0, output: usage.output_tokens ?? 0 };
      }
      run.cost_usd = (data.cost_usd as number) ?? run.cost_usd;
    } else if (event.event_type === 'ToolCall') {
      const data = event.data as Record<string, unknown>;
      const toolName = data.tool_name as string;
      const toolInput = data.tool_input as Record<string, unknown>;
      let detail = toolName;
      if (['Read', 'Edit', 'Write'].includes(toolName)) {
        detail = `${toolName}(${toolInput?.file_path ?? '?'})`;
      } else if (toolName === 'Grep') {
        detail = `Grep('${toolInput?.pattern ?? '?'}')`;
      } else if (toolName === 'Bash') {
        const cmd = (toolInput?.command as string) ?? '';
        detail = `Bash($ ${cmd.slice(0, 60)})`;
      }
      run.current_tool = detail;
    } else if (event.event_type === 'AgentCompleted') {
      run.status = 'completed';
      run.current_tool = null;
      const data = event.data as Record<string, unknown>;
      const result = data.result as Record<string, unknown> | undefined;
      if (result) {
        run.cost_usd = (result.cost_usd as number) ?? run.cost_usd;
        run.result = result;
      }
    } else if (event.event_type === 'AgentError') {
      run.status = 'error';
      run.current_tool = null;
    }

    return new Map($runs);
  });
});

export async function submitRun(agent: string, input: Record<string, unknown>): Promise<string> {
  const resp = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, input }),
  });
  const data = await resp.json();

  runs.update(($runs) => {
    $runs.set(data.run_id, {
      run_id: data.run_id,
      agent_name: agent,
      model: '',
      status: 'queued',
      cost_usd: 0,
      tokens: { input: 0, output: 0 },
      current_tool: null,
      events: [],
      result: null,
      started_at: null,
      completed_at: null,
    });
    return new Map($runs);
  });

  return data.run_id;
}

export async function cancelRun(runId: string): Promise<void> {
  await fetch(`/api/runs/${runId}`, { method: 'DELETE' });
  runs.update(($runs) => {
    const run = $runs.get(runId);
    if (run) run.status = 'cancelled';
    return new Map($runs);
  });
}

export async function killAll(): Promise<void> {
  await fetch('/api/runs', { method: 'DELETE' });
  runs.update(($runs) => {
    for (const run of $runs.values()) {
      if (run.status === 'running' || run.status === 'queued') {
        run.status = 'cancelled';
      }
    }
    return new Map($runs);
  });
}
```

- [ ] **Step 4: Create file selection store**

Create `frontend/src/lib/stores/files.ts`:

```typescript
import { writable, derived } from 'svelte/store';
import type { FileNode } from '$lib/types';

export const fileTree = writable<FileNode[]>([]);
export const searchQuery = writable('');

export const selectedFiles = derived(fileTree, ($tree) => {
  const selected: string[] = [];
  function walk(nodes: FileNode[]) {
    for (const node of nodes) {
      if (node.selected && !node.is_dir) {
        selected.push(node.path);
      }
      if (node.children) walk(node.children);
    }
  }
  walk($tree);
  return selected;
});

export function buildTreeFromPaths(paths: string[]): FileNode[] {
  const nodeMap = new Map<string, FileNode>();

  for (const path of paths) {
    const parts = path.split('/');

    for (let i = 0; i < parts.length; i++) {
      const fullPath = parts.slice(0, i + 1).join('/');
      const isLast = i === parts.length - 1;

      if (!nodeMap.has(fullPath)) {
        nodeMap.set(fullPath, {
          name: parts[i],
          path: fullPath,
          is_dir: !isLast,
          children: isLast ? undefined : [],
          selected: false,
          expanded: false,
        });
      }

      if (i > 0) {
        const parentPath = parts.slice(0, i).join('/');
        const parent = nodeMap.get(parentPath);
        const child = nodeMap.get(fullPath)!;
        if (parent && parent.children && !parent.children.includes(child)) {
          parent.children.push(child);
        }
      }
    }
  }

  const roots: FileNode[] = [];
  for (const [path, node] of nodeMap) {
    if (!path.includes('/')) {
      roots.push(node);
    }
  }

  return roots.sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export async function fetchTree(): Promise<void> {
  const resp = await fetch('/api/files/tree');
  const paths: string[] = await resp.json();
  fileTree.set(buildTreeFromPaths(paths));
}

export async function fetchGitFiles(mode: string): Promise<void> {
  const resp = await fetch(`/api/files/git/${mode}`);
  const paths: string[] = await resp.json();
  fileTree.update(($tree) => {
    function clearSelection(nodes: FileNode[]) {
      for (const node of nodes) {
        node.selected = false;
        if (node.children) clearSelection(node.children);
      }
    }
    clearSelection($tree);

    const pathSet = new Set(paths);
    function selectMatches(nodes: FileNode[]) {
      for (const node of nodes) {
        if (pathSet.has(node.path)) node.selected = true;
        if (node.children) selectMatches(node.children);
      }
    }
    selectMatches($tree);
    return [...$tree];
  });
}

export function toggleNode(path: string): void {
  fileTree.update(($tree) => {
    function walk(nodes: FileNode[]) {
      for (const node of nodes) {
        if (node.path === path) {
          node.selected = !node.selected;
          if (node.is_dir && node.children) {
            function setAll(nodes: FileNode[], val: boolean) {
              for (const n of nodes) {
                n.selected = val;
                if (n.children) setAll(n.children, val);
              }
            }
            setAll(node.children, node.selected);
          }
          return;
        }
        if (node.children) walk(node.children);
      }
    }
    walk($tree);
    return [...$tree];
  });
}

export function toggleExpand(path: string): void {
  fileTree.update(($tree) => {
    function walk(nodes: FileNode[]) {
      for (const node of nodes) {
        if (node.path === path) {
          node.expanded = !node.expanded;
          return;
        }
        if (node.children) walk(node.children);
      }
    }
    walk($tree);
    return [...$tree];
  });
}
```

- [ ] **Step 5: Create fixer queue store**

Create `frontend/src/lib/stores/queue.ts`:

```typescript
import { writable, derived } from 'svelte/store';
import type { QueueItem, Finding } from '$lib/types';

export const queue = writable<QueueItem[]>([]);

export const selectedCount = derived(queue, ($queue) =>
  $queue.filter((item) => item.selected).length,
);

export const severityCounts = derived(queue, ($queue) => ({
  high: $queue.filter((i) => i.severity === 'high').length,
  medium: $queue.filter((i) => i.severity === 'medium').length,
  low: $queue.filter((i) => i.severity === 'low').length,
  info: $queue.filter((i) => i.severity === 'info').length,
}));

export function addFindings(findings: Finding[], sourceAgent: string, sourceRunId: string): void {
  queue.update(($queue) => [
    ...$queue,
    ...findings.map((f) => ({
      ...f,
      source_agent: sourceAgent,
      source_run_id: sourceRunId,
      selected: true,
    })),
  ]);
}

export function removeItem(index: number): void {
  queue.update(($queue) => $queue.filter((_, i) => i !== index));
}

export function toggleItem(index: number): void {
  queue.update(($queue) => {
    $queue[index].selected = !$queue[index].selected;
    return [...$queue];
  });
}

export function selectAll(): void {
  queue.update(($queue) => {
    $queue.forEach((item) => (item.selected = true));
    return [...$queue];
  });
}

export function clearQueue(): void {
  queue.set([]);
}

export function getSelectedItems(): QueueItem[] {
  let items: QueueItem[] = [];
  queue.subscribe(($queue) => {
    items = $queue.filter((item) => item.selected);
  })();
  return items;
}
```

- [ ] **Step 6: Create agents store**

Create `frontend/src/lib/stores/agents.ts`:

```typescript
import { writable } from 'svelte/store';
import type { AgentMeta } from '$lib/types';

export const agents = writable<AgentMeta[]>([]);

export async function fetchAgents(): Promise<void> {
  const resp = await fetch('/api/agents');
  const data: AgentMeta[] = await resp.json();
  agents.set(data);
}
```

- [ ] **Step 7: Verify the build still works**

Run:
```bash
cd /home/jwhiteley/git/codemonkeys/frontend
npm run build
```
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat(dashboard): add TypeScript types and Svelte stores for runs, files, queue, agents"
```

---

## Task 9: TopBar and AgentLauncher Components

The header bar and agent launch controls.

**Files:**
- Create: `frontend/src/lib/components/TopBar.svelte`
- Create: `frontend/src/lib/components/AgentLauncher.svelte`

- [ ] **Step 1: Create TopBar component**

Create `frontend/src/lib/components/TopBar.svelte`:

```svelte
<script lang="ts">
  import { sessionCost } from '$lib/stores/runs';

  function formatCost(cost: number): string {
    return `$${cost.toFixed(cost < 0.01 ? 4 : 2)}`;
  }
</script>

<header class="topbar">
  <div class="brand">
    <span class="logo">🐒</span>
    <span class="title">Codemonkeys</span>
  </div>
  <div class="session-cost">
    <span class="label">Session cost:</span>
    <span class="value">{formatCost($sessionCost)}</span>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 2px solid var(--border);
    background: var(--bg-raised);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .logo { font-size: 18px; }
  .title { font-weight: 700; font-size: 16px; }
  .label { font-size: 12px; color: var(--text-dim); margin-right: 8px; }
  .value { font-size: 14px; font-weight: 600; color: var(--green); }
</style>
```

- [ ] **Step 2: Create AgentLauncher component**

Create `frontend/src/lib/components/AgentLauncher.svelte`:

```svelte
<script lang="ts">
  import { agents } from '$lib/stores/agents';
  import { selectedFiles } from '$lib/stores/files';
  import { submitRun, killAll } from '$lib/stores/runs';

  let selectedAgent = $state('');

  $effect(() => {
    if ($agents.length > 0 && !selectedAgent) {
      selectedAgent = $agents[0].name;
    }
  });

  async function handleRun() {
    if (!selectedAgent || $selectedFiles.length === 0) return;
    await submitRun(selectedAgent, { files: $selectedFiles });
  }

  async function handleKillAll() {
    await killAll();
  }
</script>

<div class="launcher">
  <select bind:value={selectedAgent}>
    {#each $agents as agent}
      <option value={agent.name}>{agent.description || agent.name}</option>
    {/each}
  </select>

  <button class="run-btn" onclick={handleRun} disabled={$selectedFiles.length === 0}>
    ▶ Run
  </button>

  <div class="divider"></div>

  <button class="kill-btn" onclick={handleKillAll}>
    Kill All
  </button>
</div>

<style>
  .launcher {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
  }
  select {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
  }
  .run-btn {
    background: var(--accent);
    color: white;
    border: none;
    padding: 6px 20px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
  }
  .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .divider { width: 1px; height: 24px; background: var(--border); }
  .kill-btn {
    background: transparent;
    color: var(--red);
    border: 1px solid var(--red);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
  }
  .kill-btn:hover { background: rgba(239, 68, 68, 0.1); }
</style>
```

- [ ] **Step 3: Verify build**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/TopBar.svelte frontend/src/lib/components/AgentLauncher.svelte
git commit -m "feat(dashboard): add TopBar and AgentLauncher components"
```

---

## Task 10: AgentCard and EventLog Components

The core monitoring UI — compact and expanded card states with live event streaming.

**Files:**
- Create: `frontend/src/lib/components/AgentCard.svelte`
- Create: `frontend/src/lib/components/EventLog.svelte`
- Create: `frontend/src/lib/components/AgentMonitor.svelte`

- [ ] **Step 1: Create EventLog component**

Create `frontend/src/lib/components/EventLog.svelte`:

```svelte
<script lang="ts">
  import type { AgentEvent } from '$lib/types';

  interface Props {
    events: AgentEvent[];
    startedAt: number | null;
  }

  let { events, startedAt }: Props = $props();

  function formatTime(timestamp: number): string {
    if (!startedAt) return '00:00.0';
    const elapsed = timestamp - startedAt;
    const mins = Math.floor(elapsed / 60);
    const secs = (elapsed % 60).toFixed(1);
    return mins > 0 ? `${mins}:${secs.padStart(4, '0')}` : secs.padStart(4, '0');
  }

  function eventColor(type: string): string {
    if (type === 'ToolCall' || type === 'ToolResult') return 'var(--yellow)';
    if (type === 'ThinkingOutput') return 'var(--purple)';
    if (type === 'TextOutput') return 'var(--green)';
    if (type === 'AgentStarted') return 'var(--accent)';
    if (type === 'ToolDenied') return 'var(--red)';
    if (type === 'RateLimitHit') return 'var(--red)';
    return 'var(--text-dim)';
  }

  function eventLabel(type: string): string {
    const labels: Record<string, string> = {
      AgentStarted: 'START',
      ToolCall: 'TOOL',
      ToolResult: 'RESULT',
      ToolDenied: 'DENIED',
      ThinkingOutput: 'THINK',
      TextOutput: 'TEXT',
      TokenUpdate: 'TOKENS',
      RateLimitHit: 'RATE',
    };
    return labels[type] ?? type;
  }

  function eventDetail(event: AgentEvent): string {
    const d = event.data as Record<string, unknown>;
    if (event.event_type === 'AgentStarted') return `Agent started — model: ${d.model}`;
    if (event.event_type === 'ToolCall') {
      const name = d.tool_name as string;
      const input = d.tool_input as Record<string, unknown>;
      if (['Read', 'Edit', 'Write'].includes(name)) return `${name}(${input?.file_path ?? '?'})`;
      if (name === 'Grep') return `Grep('${input?.pattern ?? '?'}')`;
      if (name === 'Bash') return `Bash($ ${((input?.command as string) ?? '').slice(0, 80)})`;
      return name;
    }
    if (event.event_type === 'ToolResult') {
      const output = (d.output as string) ?? '';
      return `→ ${output.slice(0, 100)}${output.length > 100 ? '...' : ''}`;
    }
    if (event.event_type === 'ThinkingOutput') return (d.text as string)?.slice(0, 200) ?? '';
    if (event.event_type === 'TextOutput') return (d.text as string)?.slice(0, 200) ?? '';
    if (event.event_type === 'ToolDenied') return `DENIED: ${d.tool_name}(${d.command})`;
    if (event.event_type === 'RateLimitHit') return `Rate limited — waiting ${d.wait_seconds}s`;
    return '';
  }

  const displayEvents = $derived(
    events.filter((e) => !['TokenUpdate', 'RawMessage'].includes(e.event_type))
  );
</script>

<div class="event-log">
  {#each displayEvents as event}
    <div class="event-line">
      <span class="time">{formatTime(event.timestamp)}</span>
      <span class="badge" style="color: {eventColor(event.event_type)}">{eventLabel(event.event_type)}</span>
      <span class="detail">{eventDetail(event)}</span>
    </div>
  {/each}
</div>

<style>
  .event-log {
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid rgba(129, 140, 248, 0.2);
    padding: 12px 16px;
    max-height: 260px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.9;
  }
  .event-line { display: flex; gap: 8px; }
  .time { color: var(--text-dim); min-width: 42px; }
  .badge { font-weight: 600; min-width: 50px; }
  .detail { color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
```

- [ ] **Step 2: Create AgentCard component**

Create `frontend/src/lib/components/AgentCard.svelte`:

```svelte
<script lang="ts">
  import type { RunState } from '$lib/types';
  import { selectedRunId } from '$lib/stores/runs';
  import EventLog from './EventLog.svelte';

  interface Props {
    run: RunState;
  }

  let { run }: Props = $props();
  let expanded = $derived($selectedRunId === run.run_id);

  function handleClick() {
    selectedRunId.update((current) => (current === run.run_id ? null : run.run_id));
  }

  function statusClass(status: string): string {
    return `status-${status}`;
  }

  function formatTokens(n: number): string {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  }

  function formatCost(cost: number): string {
    return `$${cost.toFixed(cost < 0.01 ? 4 : 3)}`;
  }

  function formatDuration(run: RunState): string {
    if (!run.started_at || !run.completed_at) return '';
    const secs = run.completed_at - run.started_at;
    return secs >= 60 ? `${(secs / 60).toFixed(1)}m` : `${secs.toFixed(1)}s`;
  }

  function findingCount(run: RunState): number | null {
    if (run.status !== 'completed' || !run.result) return null;
    const result = run.result as Record<string, unknown>;
    const output = result.output as Record<string, unknown> | undefined;
    if (!output) return null;
    const results = output.results as unknown[] | undefined;
    return results?.length ?? null;
  }
</script>

<div
  class="card {statusClass(run.status)}"
  class:expanded
  onclick={handleClick}
  role="button"
  tabindex="0"
  onkeydown={(e) => e.key === 'Enter' && handleClick()}
>
  <div class="card-header">
    <div class="left">
      <div class="status-dot"></div>
      <span class="agent-name">{run.agent_name}</span>
      <span class="model-badge">{run.model}</span>
      {#if run.status === 'queued'}
        <span class="queue-label">queued</span>
      {/if}
      {#if expanded}
        <span class="expand-indicator">▾ expanded</span>
      {/if}
    </div>
    <div class="right">
      {#if run.status === 'completed'}
        <span class="duration">{formatDuration(run)}</span>
      {/if}
      <span class="cost">{formatCost(run.cost_usd)}</span>
    </div>
  </div>

  {#if run.status === 'running' || run.status === 'completed'}
    <div class="card-meta">
      <span class="tokens">⚡ {formatTokens(run.tokens.input)} in / {formatTokens(run.tokens.output)} out</span>
      {#if run.status === 'running' && run.current_tool}
        <span class="current-tool">{run.current_tool}</span>
      {/if}
      {#if run.status === 'completed'}
        {#if findingCount(run) !== null}
          <span class="findings">{findingCount(run)} findings</span>
        {/if}
      {/if}
    </div>
  {/if}

  {#if run.status === 'error'}
    <div class="error-msg">
      {(run.result as string) ?? 'Unknown error'}
    </div>
  {/if}

  {#if expanded}
    <EventLog events={run.events} startedAt={run.started_at} />
  {/if}
</div>

<style>
  .card {
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: var(--accent); }
  .card.expanded { border-width: 2px; }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 16px;
  }
  .left { display: flex; align-items: center; gap: 10px; }
  .right { display: flex; align-items: center; gap: 16px; }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--border);
  }
  .status-running .status-dot { background: var(--accent); animation: pulse 1.5s infinite; }
  .status-queued .status-dot { background: transparent; border: 2px solid var(--text-dim); }
  .status-completed .status-dot { background: var(--green); }
  .status-error .status-dot { background: var(--red); }
  .status-cancelled .status-dot { background: var(--text-dim); }

  .status-running { border-color: var(--accent); background: rgba(129, 140, 248, 0.06); }
  .status-error { border-color: var(--red); background: rgba(239, 68, 68, 0.04); }
  .status-queued { opacity: 0.6; }

  .agent-name { font-weight: 600; font-size: 14px; }
  .model-badge {
    font-size: 11px;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .queue-label { font-size: 11px; color: var(--text-dim); margin-left: auto; }
  .expand-indicator { font-size: 11px; color: var(--accent); }

  .duration { font-size: 12px; color: var(--text-dim); }
  .cost { font-size: 13px; font-weight: 600; color: var(--green); }

  .card-meta {
    display: flex;
    justify-content: space-between;
    padding: 0 16px 12px;
    font-size: 12px;
    color: var(--text-dim);
  }
  .current-tool { font-family: monospace; color: var(--yellow); }
  .findings { color: var(--orange); }
  .error-msg { padding: 0 16px 12px; font-size: 12px; color: var(--red); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
</style>
```

- [ ] **Step 3: Create AgentMonitor component**

Create `frontend/src/lib/components/AgentMonitor.svelte`:

```svelte
<script lang="ts">
  import { runsByStatus } from '$lib/stores/runs';
  import AgentLauncher from './AgentLauncher.svelte';
  import AgentCard from './AgentCard.svelte';
</script>

<div class="monitor">
  <AgentLauncher />

  <div class="cards">
    {#if $runsByStatus.running.length > 0}
      <div class="section-label">RUNNING</div>
      {#each $runsByStatus.running as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.queued.length > 0}
      <div class="section-label">QUEUED</div>
      {#each $runsByStatus.queued as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.completed.length > 0}
      <div class="section-label">COMPLETED</div>
      {#each $runsByStatus.completed as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.running.length === 0 && $runsByStatus.queued.length === 0 && $runsByStatus.completed.length === 0}
      <div class="empty">
        <p>No agent runs yet.</p>
        <p class="hint">Select files on the left, pick an agent, and click Run.</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .monitor { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .cards { flex: 1; overflow-y: auto; padding: 16px; }
  .section-label {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 12px;
    margin-top: 8px;
  }
  .section-label:first-child { margin-top: 0; }
  .empty { text-align: center; padding: 60px 20px; color: var(--text-dim); }
  .hint { font-size: 12px; margin-top: 8px; }
</style>
```

- [ ] **Step 4: Verify build**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/AgentCard.svelte frontend/src/lib/components/EventLog.svelte frontend/src/lib/components/AgentMonitor.svelte
git commit -m "feat(dashboard): add AgentCard, EventLog, and AgentMonitor components"
```

---

## Task 11: FilePicker Components

File tree, git buttons, drop zone, and search.

**Files:**
- Create: `frontend/src/lib/components/FileTree.svelte`
- Create: `frontend/src/lib/components/GitButtons.svelte`
- Create: `frontend/src/lib/components/DropZone.svelte`
- Create: `frontend/src/lib/components/FilePicker.svelte`

- [ ] **Step 1: Create FileTree component**

Create `frontend/src/lib/components/FileTree.svelte`:

```svelte
<script lang="ts">
  import type { FileNode } from '$lib/types';
  import { toggleNode, toggleExpand, searchQuery } from '$lib/stores/files';

  interface Props {
    nodes: FileNode[];
    depth?: number;
  }

  let { nodes, depth = 0 }: Props = $props();

  function matchesSearch(node: FileNode, query: string): boolean {
    if (!query) return true;
    const q = query.toLowerCase();
    if (node.name.toLowerCase().includes(q)) return true;
    if (node.children) return node.children.some((c) => matchesSearch(c, q));
    return false;
  }

  const filteredNodes = $derived(
    nodes
      .filter((n) => matchesSearch(n, $searchQuery))
      .sort((a, b) => {
        if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
        return a.name.localeCompare(b.name);
      })
  );
</script>

{#each filteredNodes as node (node.path)}
  <div class="tree-node" style="padding-left: {depth * 16}px">
    <span
      class="checkbox"
      onclick|stopPropagation={() => toggleNode(node.path)}
      role="checkbox"
      aria-checked={node.selected}
      tabindex="0"
      onkeydown={(e) => e.key === ' ' && toggleNode(node.path)}
    >
      {node.selected ? '☑' : '☐'}
    </span>

    {#if node.is_dir}
      <span
        class="folder"
        onclick={() => toggleExpand(node.path)}
        role="button"
        tabindex="0"
        onkeydown={(e) => e.key === 'Enter' && toggleExpand(node.path)}
      >
        {node.expanded ? '📂' : '📁'} {node.name}/
      </span>
    {:else}
      <span class="file">{node.name}</span>
    {/if}
  </div>

  {#if node.is_dir && node.expanded && node.children}
    <svelte:self nodes={node.children} depth={depth + 1} />
  {/if}
{/each}

<style>
  .tree-node {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
    font-size: 13px;
    line-height: 1.8;
  }
  .checkbox {
    cursor: pointer;
    user-select: none;
    color: var(--text-dim);
  }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .folder { cursor: pointer; color: var(--accent); }
  .file { color: var(--text); }
</style>
```

- [ ] **Step 2: Create GitButtons component**

Create `frontend/src/lib/components/GitButtons.svelte`:

```svelte
<script lang="ts">
  import { fetchGitFiles } from '$lib/stores/files';

  let activeMode = $state('');

  async function selectMode(mode: string) {
    activeMode = mode;
    await fetchGitFiles(mode);
  }
</script>

<div class="git-buttons">
  <button class:active={activeMode === 'changed'} onclick={() => selectMode('changed')}>Changed</button>
  <button class:active={activeMode === 'staged'} onclick={() => selectMode('staged')}>Staged</button>
  <button class:active={activeMode === 'all-py'} onclick={() => selectMode('all-py')}>All .py</button>
</div>

<style>
  .git-buttons { display: flex; gap: 6px; margin-bottom: 10px; }
  button {
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
  }
  button:hover { border-color: var(--accent); color: var(--text); }
  button.active { background: var(--accent); color: white; border-color: var(--accent); }
</style>
```

- [ ] **Step 3: Create DropZone component**

Create `frontend/src/lib/components/DropZone.svelte`:

```svelte
<script lang="ts">
  let dragover = $state(false);

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragover = false;
    // File drop handling will be limited in browser context
    // For now, this is a visual placeholder
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    dragover = true;
  }

  function handleDragLeave() {
    dragover = false;
  }
</script>

<div
  class="dropzone"
  class:dragover
  ondrop={handleDrop}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  role="region"
  aria-label="Drop files here"
>
  Drop files here
</div>

<style>
  .dropzone {
    padding: 16px;
    border: 2px dashed var(--border);
    border-radius: 8px;
    text-align: center;
    font-size: 12px;
    color: var(--text-dim);
    transition: border-color 0.15s, background 0.15s;
  }
  .dragover {
    border-color: var(--accent);
    background: rgba(129, 140, 248, 0.1);
    color: var(--accent);
  }
</style>
```

- [ ] **Step 4: Create FilePicker composition**

Create `frontend/src/lib/components/FilePicker.svelte`:

```svelte
<script lang="ts">
  import { fileTree, selectedFiles, searchQuery, fetchTree } from '$lib/stores/files';
  import FileTree from './FileTree.svelte';
  import GitButtons from './GitButtons.svelte';
  import DropZone from './DropZone.svelte';
  import { onMount } from 'svelte';

  onMount(() => {
    fetchTree();
  });
</script>

<div class="picker">
  <div class="header">
    <div class="title">FILES</div>
    <GitButtons />
    <input
      class="search"
      type="text"
      placeholder="Search files..."
      bind:value={$searchQuery}
    />
  </div>

  <div class="tree">
    <FileTree nodes={$fileTree} />
  </div>

  <div class="footer">
    <div class="count">{$selectedFiles.length} files selected</div>
    <DropZone />
  </div>
</div>

<style>
  .picker { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .title { font-weight: 600; font-size: 13px; margin-bottom: 10px; }
  .search {
    width: 100%;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    margin-top: 10px;
  }
  .search::placeholder { color: var(--text-dim); }
  .tree { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .count { font-size: 12px; color: var(--text-dim); margin-bottom: 8px; }
</style>
```

- [ ] **Step 5: Verify build**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/FileTree.svelte frontend/src/lib/components/GitButtons.svelte frontend/src/lib/components/DropZone.svelte frontend/src/lib/components/FilePicker.svelte
git commit -m "feat(dashboard): add FilePicker with tree, git buttons, search, and drop zone"
```

---

## Task 12: Results Panel and Fixer Queue Components

The right panel with tabs for viewing findings and managing the fix queue.

**Files:**
- Create: `frontend/src/lib/components/FindingsList.svelte`
- Create: `frontend/src/lib/components/FixerQueue.svelte`
- Create: `frontend/src/lib/components/ResultsPanel.svelte`

- [ ] **Step 1: Create FindingsList component**

Create `frontend/src/lib/components/FindingsList.svelte`:

```svelte
<script lang="ts">
  import type { Finding } from '$lib/types';

  interface Props {
    findings: Finding[];
    checkedIndices: Set<number>;
    onToggle: (index: number) => void;
  }

  let { findings, checkedIndices, onToggle }: Props = $props();

  function severityColor(severity: string): string {
    const colors: Record<string, string> = {
      high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--blue)', info: 'var(--text-dim)',
    };
    return colors[severity] ?? 'var(--text-dim)';
  }
</script>

{#each findings as finding, i}
  <div class="finding">
    <div class="finding-header">
      <div class="left">
        <span
          class="checkbox"
          onclick={() => onToggle(i)}
          role="checkbox"
          aria-checked={checkedIndices.has(i)}
          tabindex="0"
          onkeydown={(e) => e.key === ' ' && onToggle(i)}
        >
          {checkedIndices.has(i) ? '☑' : '☐'}
        </span>
        <div>
          <div class="title">{finding.title}</div>
          <div class="location">{finding.file}{finding.line ? `:${finding.line}` : ''}</div>
        </div>
      </div>
      <span class="severity" style="color: {severityColor(finding.severity)}; border-color: {severityColor(finding.severity)}">
        {finding.severity}
      </span>
    </div>
    {#if finding.description}
      <div class="description">{finding.description}</div>
    {/if}
  </div>
{/each}

<style>
  .finding {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
  }
  .finding-header { display: flex; justify-content: space-between; align-items: start; }
  .left { display: flex; gap: 8px; align-items: start; }
  .checkbox { cursor: pointer; font-size: 14px; color: var(--text-dim); margin-top: 1px; }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .title { font-size: 13px; font-weight: 600; }
  .location { font-size: 11px; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
  .severity {
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.05);
  }
  .description { font-size: 12px; color: var(--text-dim); margin-top: 8px; line-height: 1.5; }
</style>
```

- [ ] **Step 2: Create FixerQueue component**

Create `frontend/src/lib/components/FixerQueue.svelte`:

```svelte
<script lang="ts">
  import {
    queue, selectedCount, severityCounts,
    removeItem, toggleItem, selectAll, clearQueue, getSelectedItems,
  } from '$lib/stores/queue';
  import { submitRun } from '$lib/stores/runs';

  function severityColor(severity: string): string {
    const colors: Record<string, string> = {
      high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--blue)', info: 'var(--text-dim)',
    };
    return colors[severity] ?? 'var(--text-dim)';
  }

  async function handleFix() {
    const items = getSelectedItems();
    if (items.length === 0) return;
    const findings = items.map(({ source_agent, source_run_id, selected, ...f }) => f);
    await submitRun('make_fixer', { findings });
  }

  function exportJson() {
    const items = getSelectedItems();
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'findings.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="fixer-queue">
  <div class="status-bar">
    <span class="count">{$queue.length} items queued</span>
    <div class="severity-badges">
      {#if $severityCounts.high > 0}
        <span class="badge" style="color: var(--red)">{$severityCounts.high} high</span>
      {/if}
      {#if $severityCounts.medium > 0}
        <span class="badge" style="color: var(--yellow)">{$severityCounts.medium} med</span>
      {/if}
      {#if $severityCounts.low > 0}
        <span class="badge" style="color: var(--blue)">{$severityCounts.low} low</span>
      {/if}
    </div>
  </div>

  <div class="items">
    {#each $queue as item, i (i)}
      <div class="item" style="border-left: 3px solid {severityColor(item.severity)}">
        <div class="item-header">
          <div class="left">
            <span
              class="checkbox"
              onclick={() => toggleItem(i)}
              role="checkbox"
              aria-checked={item.selected}
              tabindex="0"
              onkeydown={(e) => e.key === ' ' && toggleItem(i)}
            >
              {item.selected ? '☑' : '☐'}
            </span>
            <div>
              <div class="title">{item.title}</div>
              <div class="location">{item.file}{item.line ? `:${item.line}` : ''}</div>
            </div>
          </div>
          <button class="remove" onclick={() => removeItem(i)}>×</button>
        </div>
      </div>
    {/each}

    {#if $queue.length === 0}
      <div class="empty">No items in queue. Select findings from the Results tab and add them here.</div>
    {/if}
  </div>

  <div class="actions">
    <button class="fix-btn" onclick={handleFix} disabled={$selectedCount === 0}>
      🔧 Fix Selected ({$selectedCount})
    </button>
    <div class="secondary-actions">
      <button onclick={selectAll}>Select All</button>
      <button onclick={clearQueue}>Clear Queue</button>
      <button onclick={exportJson}>Export JSON</button>
    </div>
  </div>
</div>

<style>
  .fixer-queue { display: flex; flex-direction: column; height: 100%; }
  .status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(249, 115, 22, 0.06);
  }
  .count { font-size: 12px; font-weight: 600; color: var(--orange); }
  .severity-badges { display: flex; gap: 6px; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); }
  .items { flex: 1; overflow-y: auto; padding: 12px; }
  .item {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
  }
  .item-header { display: flex; justify-content: space-between; align-items: start; }
  .left { display: flex; gap: 8px; align-items: start; }
  .checkbox { cursor: pointer; font-size: 14px; color: var(--text-dim); }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .title { font-size: 13px; font-weight: 600; }
  .location { font-size: 11px; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
  .remove { background: none; border: none; color: var(--text-dim); font-size: 14px; padding: 0 4px; }
  .remove:hover { color: var(--red); }
  .empty { text-align: center; padding: 30px; color: var(--text-dim); font-size: 12px; }
  .actions { padding: 12px 16px; border-top: 1px solid var(--border); background: var(--bg-raised); }
  .fix-btn {
    width: 100%;
    background: var(--orange);
    color: white;
    border: none;
    padding: 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
  }
  .fix-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .secondary-actions { display: flex; gap: 8px; }
  .secondary-actions button {
    flex: 1;
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 6px;
    border-radius: 6px;
    font-size: 11px;
  }
</style>
```

- [ ] **Step 3: Create ResultsPanel component**

Create `frontend/src/lib/components/ResultsPanel.svelte`:

```svelte
<script lang="ts">
  import type { Finding } from '$lib/types';
  import { selectedRun } from '$lib/stores/runs';
  import { addFindings } from '$lib/stores/queue';
  import { queue } from '$lib/stores/queue';
  import FindingsList from './FindingsList.svelte';
  import FixerQueue from './FixerQueue.svelte';

  let activeTab = $state<'results' | 'queue'>('results');
  let checkedIndices = $state(new Set<number>());

  function getFindings(): Finding[] {
    if (!$selectedRun?.result) return [];
    const result = $selectedRun.result as Record<string, unknown>;
    const output = result.output as Record<string, unknown> | undefined;
    if (!output?.results) return [];
    return output.results as Finding[];
  }

  const findings = $derived(getFindings());

  function toggleFinding(index: number) {
    checkedIndices = new Set(checkedIndices);
    if (checkedIndices.has(index)) {
      checkedIndices.delete(index);
    } else {
      checkedIndices.add(index);
    }
  }

  function handleAddToQueue() {
    if (!$selectedRun) return;
    const selected = findings.filter((_, i) => checkedIndices.has(i));
    addFindings(selected, $selectedRun.agent_name, $selectedRun.run_id);
    checkedIndices = new Set();
    activeTab = 'queue';
  }

  function exportFindings() {
    const blob = new Blob([JSON.stringify(findings, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'findings.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="results-panel">
  <div class="tabs">
    <button class="tab" class:active={activeTab === 'results'} onclick={() => activeTab = 'results'}>
      Results
    </button>
    <button class="tab" class:active={activeTab === 'queue'} onclick={() => activeTab = 'queue'}>
      Fixer Queue
      {#if $queue.length > 0}
        <span class="queue-badge">{$queue.length}</span>
      {/if}
    </button>
  </div>

  {#if activeTab === 'results'}
    <div class="results-content">
      {#if $selectedRun}
        <div class="results-header">
          <span class="agent-label">{$selectedRun.agent_name}</span>
          {#if $selectedRun.status === 'running'}
            <span class="streaming">streaming...</span>
          {/if}
        </div>

        {#if findings.length > 0}
          <div class="findings-list">
            <FindingsList {findings} {checkedIndices} onToggle={toggleFinding} />
          </div>

          <div class="results-actions">
            <button class="add-btn" onclick={handleAddToQueue} disabled={checkedIndices.size === 0}>
              Add to Queue ({checkedIndices.size})
            </button>
            <button class="export-btn" onclick={exportFindings}>Export</button>
          </div>
        {:else if $selectedRun.status === 'completed'}
          <div class="empty">No findings.</div>
        {:else}
          <div class="empty">Results will appear as the agent completes analysis...</div>
        {/if}
      {:else}
        <div class="empty">Click an agent card to view its results.</div>
      {/if}
    </div>
  {:else}
    <FixerQueue />
  {/if}
</div>

<style>
  .results-panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .tabs { display: flex; border-bottom: 1px solid var(--border); background: var(--bg-raised); }
  .tab {
    flex: 1;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
    text-align: center;
    background: none;
    border: none;
    color: var(--text-dim);
    border-bottom: 2px solid transparent;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab.active:last-child { color: var(--orange); border-bottom-color: var(--orange); }
  .queue-badge {
    background: var(--orange);
    color: white;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    margin-left: 4px;
  }
  .results-content { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(129, 140, 248, 0.06);
  }
  .agent-label { font-size: 12px; font-weight: 600; }
  .streaming { font-size: 11px; color: var(--text-dim); }
  .findings-list { flex: 1; overflow-y: auto; padding: 12px; }
  .results-actions {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .add-btn {
    flex: 1;
    background: var(--orange);
    color: white;
    border: none;
    padding: 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
  }
  .add-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .export-btn {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
  }
  .empty { text-align: center; padding: 40px 20px; color: var(--text-dim); font-size: 12px; }
</style>
```

- [ ] **Step 4: Verify build**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/FindingsList.svelte frontend/src/lib/components/FixerQueue.svelte frontend/src/lib/components/ResultsPanel.svelte
git commit -m "feat(dashboard): add FindingsList, FixerQueue, and ResultsPanel components"
```

---

## Task 13: Wire Up the Root Page

Connect all components into the three-panel layout with WebSocket initialization.

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Update root page to compose all components**

Replace the contents of `frontend/src/routes/+page.svelte`:

```svelte
<script lang="ts">
  import '../app.css';
  import { onMount, onDestroy } from 'svelte';
  import { connect, disconnect } from '$lib/stores/ws';
  import { fetchAgents } from '$lib/stores/agents';
  import TopBar from '$lib/components/TopBar.svelte';
  import FilePicker from '$lib/components/FilePicker.svelte';
  import AgentMonitor from '$lib/components/AgentMonitor.svelte';
  import ResultsPanel from '$lib/components/ResultsPanel.svelte';

  onMount(() => {
    connect();
    fetchAgents();
  });

  onDestroy(() => {
    disconnect();
  });
</script>

<div class="dashboard">
  <TopBar />
  <main class="panels">
    <aside class="file-picker">
      <FilePicker />
    </aside>
    <section class="agent-monitor">
      <AgentMonitor />
    </section>
    <aside class="results-panel">
      <ResultsPanel />
    </aside>
  </main>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .panels {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    flex: 1;
    overflow: hidden;
  }
  .file-picker {
    border-right: 1px solid var(--border);
    overflow: hidden;
  }
  .agent-monitor { overflow: hidden; }
  .results-panel {
    border-left: 1px solid var(--border);
    overflow: hidden;
  }
</style>
```

- [ ] **Step 2: Build and verify**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: PASS — built output in `codemonkeys/dashboard/static/`.

- [ ] **Step 3: End-to-end smoke test**

Start the backend:
```bash
cd /home/jwhiteley/git/codemonkeys
uv run codemonkeys-dashboard --port 8000
```

Open `http://localhost:8000` in a browser. Verify:
- Three-panel layout renders with dark theme
- 🐒 Codemonkeys branding in top bar
- File tree loads and shows project files
- Agent dropdown is populated with registered agents
- Git shortcut buttons work (Changed/Staged/All .py)
- WebSocket connects (check browser console, no errors)

Kill the server after verifying.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(dashboard): wire up root page with all components"
```

---

## Task 14: Run All Tests and Final Verification

Run the full test suite and verify everything works together.

**Files:** None new — verification only.

- [ ] **Step 1: Run the full Python test suite**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pytest tests/ -v`
Expected: All tests pass (existing + new registry, orchestrator, server tests).

- [ ] **Step 2: Run linting**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run ruff check --fix . && uv run ruff format .`
Expected: Clean.

- [ ] **Step 3: Run type checking**

Run: `cd /home/jwhiteley/git/codemonkeys && uv run pyright .`
Expected: No errors in new code (existing codebase may have pre-existing issues).

- [ ] **Step 4: Build frontend**

Run: `cd /home/jwhiteley/git/codemonkeys/frontend && npm run build`
Expected: Clean build.

- [ ] **Step 5: Full integration test**

Start the server: `uv run codemonkeys-dashboard --port 8000`

In the browser at `http://localhost:8000`:
1. Select a Python file in the file tree
2. Pick "Python File Reviewer" from the agent dropdown
3. Click Run
4. Watch the agent card appear with status, tokens, cost, and current tool
5. When it completes, click the card to see results in the right panel
6. Check some findings, click "Add to Queue"
7. Switch to the Fixer Queue tab, verify items appear
8. Click "Fix Selected" to launch the fixer agent
9. Verify the fixer appears as a new running card

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```
