"""FastAPI application factory and routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from codemonkeys.web.models import (
    ChatMessageRequest,
    ChatStartRequest,
    CwdUpdate,
    RunRequest,
    SessionStatus,
)
from codemonkeys.web.session_manager import SessionManager

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(cwd: str | None = None) -> FastAPI:
    app = FastAPI(title="codemonkeys")
    manager = SessionManager()
    if cwd:
        manager.set_cwd(cwd)

    # ── Working directory ──

    @app.get("/cwd")
    def get_cwd():
        return {"path": manager.cwd}

    @app.put("/cwd")
    def set_cwd(body: CwdUpdate):
        try:
            resolved = manager.set_cwd(body.path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"path": resolved}

    # ── Agents ──

    @app.get("/agents")
    def list_agents():
        return manager.list_agents()

    # ── Saved outputs ──

    @app.get("/saved-outputs")
    def list_saved_outputs():
        return manager.list_saved_outputs()

    @app.get("/saved-outputs/{filename}")
    def get_saved_output(filename: str):
        content = manager.get_saved_output(filename)
        if content is None:
            raise HTTPException(404, "Output not found")
        return PlainTextResponse(content)

    # ── Sessions ──

    @app.post("/sessions/run", status_code=201)
    async def start_run(request: RunRequest) -> SessionStatus:
        try:
            return await manager.start_run(
                agent_key=request.agent_key,
                prompt=request.prompt,
                context_files=request.context_files,
                token_budget=request.token_budget,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/sessions/chat", status_code=201)
    async def start_chat(request: ChatStartRequest) -> SessionStatus:
        try:
            return await manager.start_chat(
                agent_key=request.agent_key,
                message=request.message,
                context_files=request.context_files,
                token_budget=request.token_budget,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/sessions/{session_id}/message")
    async def send_chat_message(
        session_id: str, request: ChatMessageRequest,
    ):
        ok = await manager.send_chat_message(session_id, request.message)
        if not ok:
            raise HTTPException(400, "Cannot send message to this session")
        return {"ok": True}

    @app.post("/sessions/{session_id}/end")
    async def end_chat(session_id: str):
        filename = await manager.end_chat(session_id)
        if filename is None:
            raise HTTPException(400, "Cannot end this session")
        return {"output_file": filename}

    @app.post("/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str):
        ok = await manager.cancel_session(session_id)
        if not ok:
            raise HTTPException(404, "Session not found")
        return {"ok": True}

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> SessionStatus:
        status = manager.get_session(session_id)
        if not status:
            raise HTTPException(404, "Session not found")
        return status

    # ── WebSocket ──

    @app.websocket("/sessions/{session_id}/ws")
    async def session_ws(ws: WebSocket, session_id: str):
        await ws.accept()
        manager.register_ws(session_id, ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            manager.unregister_ws(session_id, ws)

    # ── Static ──

    @app.get("/")
    def index():
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
