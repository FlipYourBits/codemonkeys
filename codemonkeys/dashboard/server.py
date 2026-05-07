"""FastAPI server — REST endpoints, WebSocket hub, static file serving."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from codemonkeys.dashboard.orchestrator import Orchestrator
from codemonkeys.dashboard.registry import discover_agents


STATIC_DIR = Path(__file__).parent / "static"


def _git_files_changed() -> list[str]:
    unstaged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True,
        text=True,
    )
    all_files = set(
        unstaged.stdout.strip().splitlines() + staged.stdout.strip().splitlines()
    )
    return sorted(f for f in all_files if f and Path(f).exists())


def _git_files_staged() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        capture_output=True,
        text=True,
    )
    return sorted(
        f for f in result.stdout.strip().splitlines() if f and Path(f).exists()
    )


def _git_files_all_py() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py", "--cached"],
        capture_output=True,
        text=True,
    )
    return sorted(
        f for f in result.stdout.strip().splitlines() if f and Path(f).exists()
    )


def _file_tree() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True,
        text=True,
    )
    return sorted(f for f in result.stdout.strip().splitlines() if f)


def create_app() -> FastAPI:
    app = FastAPI(title="Codemonkeys Dashboard")
    orchestrator = Orchestrator(max_concurrent=3)
    agents = discover_agents()
    app.state.orchestrator = orchestrator

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

    @app.post("/api/runs")
    async def submit_run(body: dict):
        agent_name = body.get("agent")
        input_data = body.get("input", {})

        agent_meta = next((a for a in agents if a.name == agent_name), None)
        if agent_meta is None:
            raise HTTPException(
                status_code=404, detail=f"Agent not found: {agent_name}"
            )

        from codemonkeys.dashboard.registry import get_factory

        factory = get_factory(agent_name)
        if factory is None:
            raise HTTPException(
                status_code=404, detail=f"Factory not found: {agent_name}"
            )

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
            raise HTTPException(
                status_code=404, detail="Run not found or not cancellable"
            )
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

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
