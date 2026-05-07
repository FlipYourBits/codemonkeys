"""FastAPI server — REST endpoints, WebSocket hub, static file serving."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
