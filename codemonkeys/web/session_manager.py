"""SessionManager — single-agent execution with chat and run modes."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    MirrorErrorMessage,
    RateLimitEvent,
    ResultMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from fastapi import WebSocket

from codemonkeys.coordinators.python import _python_agents
from codemonkeys.web.models import (
    AgentInfo,
    SavedOutput,
    SessionStatus,
    WSEvent,
)


class _SessionState:
    __slots__ = (
        "session_id", "mode", "agent_key", "prompt", "status",
        "created_at", "completed_at", "cost_usd", "total_tokens",
        "input_tokens", "output_tokens",
        "token_budget", "task", "client", "text_parts", "output_file",
    )

    def __init__(
        self,
        session_id: str,
        mode: str,
        agent_key: str,
        prompt: str,
        token_budget: int,
    ) -> None:
        self.session_id = session_id
        self.mode = mode
        self.agent_key = agent_key
        self.prompt = prompt
        self.status = "running"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None
        self.cost_usd: float = 0.0
        self.total_tokens: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.token_budget = token_budget
        self.task: asyncio.Task[None] | None = None
        self.client: ClaudeSDKClient | None = None
        self.text_parts: list[str] = []
        self.output_file: str | None = None


_AGENTS_NEEDING_PROMPT = {
    "python_fixer",
    "python_implementer",
    "python_test_writer",
}

_DEFAULT_PROMPTS: dict[str, str] = {
    "changelog_reviewer": "Review the CHANGELOG against recent git history.",
    "project_memory": "Build or rebuild the project architecture document.",
    "project_memory_updater": "Update the project architecture document with recent changes.",
    "python_coverage_analyzer": "Run tests with coverage and report uncovered areas.",
    "python_dep_auditor": "Audit dependencies for known vulnerabilities.",
    "python_fixer": "",
    "python_implementer": "",
    "python_linter": "Lint and format the project.",
    "python_quality_reviewer": "Review code quality across the project.",
    "python_security_auditor": "Review the project for security vulnerabilities.",
    "python_test_runner": "Run the test suite.",
    "python_test_writer": "",
    "python_type_checker": "Run type checking on the project.",
    "readme_reviewer": "Review the README for accuracy and completeness.",
}


class SessionManager:
    """Manages single-agent sessions in chat or run mode."""

    def __init__(self) -> None:
        self._cwd: str | None = None
        self._output_dir: Path | None = None
        self._agent_defs: dict[str, AgentDefinition] = _python_agents()
        self._sessions: dict[str, _SessionState] = {}
        self._ws_clients: dict[str, set[WebSocket]] = {}

    @property
    def cwd(self) -> str | None:
        return self._cwd

    def set_cwd(self, path: str) -> str:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            msg = f"Not a directory: {resolved}"
            raise ValueError(msg)
        self._cwd = str(resolved)
        self._output_dir = resolved / "docs" / "codemonkeys" / "runs"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._cwd

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(
                key=key,
                description=agent.description or "",
                model=agent.model,
                needs_prompt=key in _AGENTS_NEEDING_PROMPT,
                default_prompt=_DEFAULT_PROMPTS.get(key, ""),
            )
            for key, agent in self._agent_defs.items()
        ]

    def list_saved_outputs(self) -> list[SavedOutput]:
        if not self._output_dir or not self._output_dir.is_dir():
            return []
        outputs: list[SavedOutput] = []
        for path in sorted(self._output_dir.glob("*.md"), reverse=True):
            match = re.match(
                r"(\d{4}-\d{2}-\d{2}_\d{6})_(.+)\.md$", path.name,
            )
            if not match:
                continue
            timestamp_str, agent_key = match.groups()
            created = datetime.strptime(
                timestamp_str, "%Y-%m-%d_%H%M%S",
            ).astimezone()
            outputs.append(SavedOutput(
                filename=path.name,
                agent_key=agent_key,
                created_at=created.isoformat(),
                size_bytes=path.stat().st_size,
            ))
        return outputs

    def get_saved_output(self, filename: str) -> str | None:
        if not self._output_dir:
            return None
        path = self._output_dir / filename
        if not path.is_file() or not path.name.endswith(".md"):
            return None
        return path.read_text()

    def get_session(self, session_id: str) -> SessionStatus | None:
        state = self._sessions.get(session_id)
        if not state:
            return None
        return self._status(state)

    # ── Run mode ──

    def _require_cwd(self) -> str:
        if not self._cwd:
            msg = "Set a working directory first"
            raise ValueError(msg)
        return self._cwd

    async def start_run(
        self,
        agent_key: str,
        prompt: str,
        context_files: list[str],
        token_budget: int,
    ) -> SessionStatus:
        cwd = self._require_cwd()

        if agent_key not in self._agent_defs:
            msg = f"Unknown agent: {agent_key}"
            raise ValueError(msg)

        if not prompt:
            prompt = _DEFAULT_PROMPTS.get(agent_key, "")
        if not prompt and agent_key in _AGENTS_NEEDING_PROMPT:
            msg = f"Agent {agent_key} requires a prompt"
            raise ValueError(msg)
        if not prompt:
            prompt = f"Run {agent_key}."

        session_id = uuid.uuid4().hex[:12]
        state = _SessionState(session_id, "run", agent_key, prompt, token_budget)
        self._sessions[session_id] = state

        full_prompt = self._build_prompt(prompt, context_files)

        await self._broadcast(WSEvent(
            type="session_started", session_id=session_id,
            data={
                "mode": "run",
                "agent_key": agent_key,
                "context_files": context_files,
                "prompt": full_prompt,
            },
        ))

        state.task = asyncio.create_task(
            self._execute_run(state, full_prompt, cwd),
        )
        return self._status(state)

    async def _execute_run(
        self, state: _SessionState, prompt: str, cwd: str,
    ) -> None:
        agent = self._agent_defs[state.agent_key]
        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=agent.tools or [],
            disallowed_tools=agent.disallowedTools or [],
            mcp_servers={},
            skills=[],
            include_partial_messages=True,
        )

        try:
            async def _prompt_gen() -> Any:
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                }

            async for message in query(prompt=_prompt_gen(), options=options):
                await self._handle_message(state, message)

            state.status = "completed"
        except asyncio.CancelledError:
            state.status = "cancelled"
            await self._broadcast(WSEvent(
                type="session_cancelled", session_id=state.session_id,
            ))
            return
        except Exception as exc:
            state.status = "failed"
            await self._broadcast(WSEvent(
                type="error", session_id=state.session_id,
                data={"message": str(exc)},
            ))
            return
        finally:
            state.completed_at = datetime.now(timezone.utc).isoformat()
            state.task = None

        state.output_file = self._save_output(state)
        await self._broadcast(WSEvent(
            type="session_completed", session_id=state.session_id,
            data={
                "status": state.status,
                "total_tokens": state.total_tokens,
                "cost_usd": state.cost_usd,
                "output_file": state.output_file,
            },
        ))

    # ── Chat mode ──

    async def start_chat(
        self,
        agent_key: str,
        message: str,
        context_files: list[str],
        token_budget: int,
    ) -> SessionStatus:
        cwd = self._require_cwd()

        if agent_key not in self._agent_defs:
            msg = f"Unknown agent: {agent_key}"
            raise ValueError(msg)

        session_id = uuid.uuid4().hex[:12]
        full_prompt = self._build_prompt(message, context_files)
        state = _SessionState(session_id, "chat", agent_key, message, token_budget)
        self._sessions[session_id] = state

        agent = self._agent_defs[agent_key]
        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=agent.tools or [],
            disallowed_tools=agent.disallowedTools or [],
            mcp_servers={},
            skills=[],
            include_partial_messages=True,
        )

        client = ClaudeSDKClient(options)
        state.client = client

        await self._broadcast(WSEvent(
            type="session_started", session_id=session_id,
            data={
                "mode": "chat",
                "agent_key": agent_key,
                "context_files": context_files,
                "prompt": full_prompt,
            },
        ))

        try:
            await client.connect(full_prompt)
            state.task = asyncio.create_task(
                self._stream_chat_response(state),
            )
        except Exception as exc:
            state.status = "failed"
            await self._broadcast(WSEvent(
                type="error", session_id=session_id,
                data={"message": str(exc)},
            ))

        return self._status(state)

    async def send_chat_message(
        self, session_id: str, message: str,
    ) -> bool:
        state = self._sessions.get(session_id)
        if not state or state.mode != "chat" or not state.client:
            return False

        state.status = "running"
        await state.client.query(message)
        state.task = asyncio.create_task(
            self._stream_chat_response(state),
        )
        return True

    async def _stream_chat_response(self, state: _SessionState) -> None:
        try:
            async for message in state.client.receive_response():
                await self._handle_message(state, message)

            state.status = "idle"
            await self._broadcast(WSEvent(
                type="chat_turn_done", session_id=state.session_id,
                data={"total_tokens": state.total_tokens},
            ))
        except asyncio.CancelledError:
            state.status = "cancelled"
            await self._broadcast(WSEvent(
                type="session_cancelled", session_id=state.session_id,
            ))
        except Exception as exc:
            state.status = "failed"
            await self._broadcast(WSEvent(
                type="error", session_id=state.session_id,
                data={"message": str(exc)},
            ))
        finally:
            state.task = None

    async def end_chat(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        if not state or state.mode != "chat":
            return None
        if state.client:
            await state.client.disconnect()
            state.client = None
        state.status = "completed"
        state.completed_at = datetime.now(timezone.utc).isoformat()
        state.output_file = self._save_output(state)
        await self._broadcast(WSEvent(
            type="session_completed", session_id=state.session_id,
            data={
                "status": "completed",
                "total_tokens": state.total_tokens,
                "cost_usd": state.cost_usd,
                "output_file": state.output_file,
            },
        ))
        return state.output_file

    # ── Cancel ──

    async def cancel_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if not state:
            return False
        if state.task and not state.task.done():
            state.task.cancel()
        if state.client:
            try:
                await state.client.disconnect()
            except Exception:
                pass
            state.client = None
        state.status = "cancelled"
        state.completed_at = datetime.now(timezone.utc).isoformat()
        return True

    # ── Shared message handling ──

    async def _handle_message(
        self, state: _SessionState, message: object,
    ) -> None:
        sid = state.session_id

        if isinstance(message, AssistantMessage):
            await self._handle_assistant(state, message)

        elif isinstance(message, ResultMessage):
            if message.total_cost_usd:
                state.cost_usd += message.total_cost_usd
            if message.usage:
                final = _extract_tokens(message.usage)
                if final > state.total_tokens:
                    state.total_tokens = final
            await self._broadcast(WSEvent(
                type="result", session_id=sid,
                data={
                    "cost_usd": state.cost_usd,
                    "total_tokens": state.total_tokens,
                    "duration_ms": message.duration_ms,
                    "duration_api_ms": message.duration_api_ms,
                    "num_turns": message.num_turns,
                    "is_error": message.is_error,
                    "stop_reason": message.stop_reason,
                },
            ))

        elif isinstance(message, TaskStartedMessage):
            await self._broadcast(WSEvent(
                type="task_started", session_id=sid,
                data={
                    "task_id": message.task_id,
                    "description": message.description,
                    "task_type": message.task_type,
                },
            ))

        elif isinstance(message, TaskProgressMessage):
            usage = message.usage
            tokens = usage["total_tokens"] if isinstance(usage, dict) else getattr(usage, "total_tokens", 0)
            tool_uses = usage.get("tool_uses", 0) if isinstance(usage, dict) else getattr(usage, "tool_uses", 0)
            await self._broadcast(WSEvent(
                type="task_progress", session_id=sid,
                data={
                    "task_id": message.task_id,
                    "description": message.description,
                    "tokens": tokens,
                    "tool_uses": tool_uses,
                    "last_tool_name": message.last_tool_name,
                },
            ))

        elif isinstance(message, TaskNotificationMessage):
            await self._broadcast(WSEvent(
                type="task_notification", session_id=sid,
                data={
                    "task_id": message.task_id,
                    "status": message.status,
                    "summary": message.summary,
                    "usage": dict(message.usage) if message.usage else None,
                },
            ))

        elif isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            await self._broadcast(WSEvent(
                type="rate_limit", session_id=sid,
                data={
                    "status": info.status,
                    "utilization": info.utilization,
                    "rate_limit_type": info.rate_limit_type,
                    "resets_at": info.resets_at,
                },
            ))

        elif isinstance(message, MirrorErrorMessage):
            await self._broadcast(WSEvent(
                type="mirror_error", session_id=sid,
                data={"error": message.error},
            ))

        elif isinstance(message, UserMessage):
            if isinstance(message.content, str):
                await self._broadcast(WSEvent(
                    type="user_message", session_id=sid,
                    data={"content": message.content},
                ))
            else:
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        await self._broadcast(WSEvent(
                            type="tool_result", session_id=sid,
                            data={
                                "tool_use_id": block.tool_use_id,
                                "content": _tool_result_text(block.content),
                                "is_error": block.is_error,
                            },
                        ))
                    elif isinstance(block, TextBlock):
                        await self._broadcast(WSEvent(
                            type="user_message", session_id=sid,
                            data={"content": block.text},
                        ))

        elif isinstance(message, StreamEvent):
            event = message.event
            usage = event.get("usage") or {}
            if not usage:
                msg_data = event.get("message", {})
                usage = msg_data.get("usage") or {}
            if usage:
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                if inp > state.input_tokens:
                    state.input_tokens = inp
                if out > state.output_tokens:
                    state.output_tokens = out
                total = state.input_tokens + state.output_tokens
                if total > state.total_tokens:
                    state.total_tokens = total
                    await self._broadcast(WSEvent(
                        type="token_update", session_id=sid,
                        data={"tokens": state.total_tokens},
                    ))

        elif isinstance(message, SystemMessage):
            await self._broadcast(WSEvent(
                type="system_message", session_id=sid,
                data={"subtype": message.subtype, "data": message.data},
            ))

    async def _handle_assistant(
        self, state: _SessionState, message: AssistantMessage,
    ) -> None:
        sid = state.session_id
        for block in message.content:
            if isinstance(block, TextBlock):
                state.text_parts.append(block.text)
                await self._broadcast(WSEvent(
                    type="text", session_id=sid,
                    data={"text": block.text},
                ))
            elif isinstance(block, ThinkingBlock):
                await self._broadcast(WSEvent(
                    type="thinking", session_id=sid,
                    data={"thinking": block.thinking},
                ))
            elif isinstance(block, ToolUseBlock):
                await self._broadcast(WSEvent(
                    type="tool_use", session_id=sid,
                    data={
                        "name": block.name,
                        "input": block.input or {},
                        "id": block.id,
                    },
                ))
            elif isinstance(block, ToolResultBlock):
                await self._broadcast(WSEvent(
                    type="tool_result", session_id=sid,
                    data={
                        "tool_use_id": block.tool_use_id,
                        "content": _tool_result_text(block.content),
                        "is_error": block.is_error,
                    },
                ))
            elif isinstance(block, ServerToolUseBlock):
                await self._broadcast(WSEvent(
                    type="server_tool_use", session_id=sid,
                    data={
                        "name": block.name,
                        "input": block.input or {},
                        "id": block.id,
                    },
                ))
            elif isinstance(block, ServerToolResultBlock):
                await self._broadcast(WSEvent(
                    type="server_tool_result", session_id=sid,
                    data={
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                    },
                ))

        if message.usage:
            inp = message.usage.get("input_tokens", 0)
            out = message.usage.get("output_tokens", 0)
            if inp > state.input_tokens:
                state.input_tokens = inp
            if out > state.output_tokens:
                state.output_tokens = out
            total = state.input_tokens + state.output_tokens
            if total > state.total_tokens:
                state.total_tokens = total
            await self._broadcast(WSEvent(
                type="token_update", session_id=sid,
                data={
                    "tokens": state.total_tokens,
                    "model": message.model,
                    "stop_reason": message.stop_reason,
                },
            ))

    # ── WebSocket ──

    def register_ws(self, session_id: str, ws: WebSocket) -> None:
        self._ws_clients.setdefault(session_id, set()).add(ws)

    def unregister_ws(self, session_id: str, ws: WebSocket) -> None:
        clients = self._ws_clients.get(session_id)
        if clients:
            clients.discard(ws)

    async def _broadcast(self, event: WSEvent) -> None:
        clients = self._ws_clients.get(event.session_id, set())
        payload = event.model_dump_json()
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    # ── Persistence ──

    def _save_output(self, state: _SessionState) -> str:
        if not self._output_dir:
            return ""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{state.agent_key}.md"
        path = self._output_dir / filename
        content = "".join(state.text_parts)
        path.write_text(content)
        return filename

    def _build_prompt(
        self, prompt: str, context_files: list[str],
    ) -> str:
        if not context_files:
            return prompt
        sections: list[str] = []
        for filename in context_files:
            content = self.get_saved_output(filename)
            if content:
                sections.append(f"## Context: {filename}\n\n{content}")
        if not sections:
            return prompt
        context = "\n\n---\n\n".join(sections)
        return f"{context}\n\n---\n\n## Task\n\n{prompt}"

    @staticmethod
    def _status(state: _SessionState) -> SessionStatus:
        return SessionStatus(
            session_id=state.session_id,
            mode=state.mode,
            agent_key=state.agent_key,
            status=state.status,
            prompt=state.prompt,
            created_at=state.created_at,
            completed_at=state.completed_at,
            cost_usd=state.cost_usd or None,
            total_tokens=state.total_tokens,
            token_budget=state.token_budget,
            output_file=state.output_file,
        )


def _extract_tokens(usage: dict[str, Any]) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
    ) or usage.get("total_tokens", 0)


def _tool_result_text(content: str | list[Any] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ToolResultBlock):
            parts.append(_tool_result_text(block.content))
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, dict):
            parts.append(str(block))
        elif hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "content"):
            parts.append(_tool_result_text(block.content))
        else:
            parts.append(str(block))
    return "\n".join(parts)
