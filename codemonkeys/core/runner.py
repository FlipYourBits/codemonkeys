"""Reusable agent runner with event emission, debug logging, and filesystem sandboxing."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    ToolUseBlock,
    query,
)

from codemonkeys.core.run_result import RunResult
from codemonkeys.core.sandbox import restrict
from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentProgressPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
)


def _tool_detail(block: ToolUseBlock) -> str:
    name = block.name
    tool_input = block.input or {}
    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "?")
        return f"{name}({path})"
    if name == "Grep":
        return f"Grep('{tool_input.get('pattern', '?')}')"
    if name == "Glob":
        return f"Glob({tool_input.get('pattern', tool_input.get('path', '?'))})"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash($ {cmd[:80]})" if cmd else "Bash"
    return name


def _serialize_message(message: Any) -> dict[str, Any]:
    """Serialize an SDK message to a JSON-safe dict for logging."""
    entry: dict[str, Any] = {"type": type(message).__name__}
    if isinstance(message, AssistantMessage):
        entry["usage"] = message.usage
        blocks = []
        for b in message.content:
            if isinstance(b, ToolUseBlock):
                blocks.append({"type": "tool_use", "name": b.name, "input": b.input})
            elif hasattr(b, "text"):
                blocks.append({"type": "text", "text": b.text[:500]})
            elif hasattr(b, "thinking"):
                blocks.append({"type": "thinking", "thinking": b.thinking[:500]})
        entry["content"] = blocks
    elif isinstance(message, ResultMessage):
        entry["result"] = (getattr(message, "result", "") or "")[:500]
        entry["usage"] = message.usage
        entry["cost"] = getattr(message, "total_cost_usd", None)
        entry["duration_ms"] = getattr(message, "duration_ms", 0)
    elif isinstance(message, TaskStartedMessage):
        entry["task_id"] = message.task_id
        entry["description"] = message.description
    elif isinstance(message, TaskProgressMessage):
        usage = message.usage
        entry["task_id"] = message.task_id
        entry["usage"] = (
            dict(usage)
            if isinstance(usage, dict)
            else {
                "total_tokens": getattr(usage, "total_tokens", 0),
                "tool_uses": getattr(usage, "tool_uses", 0),
            }
        )
    elif isinstance(message, TaskNotificationMessage):
        entry["task_id"] = message.task_id
        usage = message.usage
        if usage:
            entry["usage"] = (
                dict(usage)
                if isinstance(usage, dict)
                else {
                    "total_tokens": getattr(usage, "total_tokens", 0),
                }
            )
    return entry


class AgentRunner:
    """Runs agents with event emission, debug logging, and filesystem sandboxing."""

    def __init__(
        self,
        cwd: str = ".",
        emitter: EventEmitter | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self.cwd = cwd
        self._emitter = emitter
        self._log_dir = log_dir

    def _emit(self, event_type: EventType, payload: Any) -> None:
        if self._emitter:
            self._emitter.emit(event_type, payload)

    def _log_path(self, log_name: str) -> Path | None:
        if not self._log_dir:
            return None
        safe = log_name.replace("/", "__").replace("\\", "__").replace(" ", "_")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        return self._log_dir / f"{safe}_{ts}.log"

    async def run_agent(
        self,
        agent: AgentDefinition,
        prompt: str,
        *,
        output_format: dict[str, Any] | None = None,
        log_name: str = "agent",
    ) -> RunResult:
        restrict(self.cwd)

        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=self.cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=agent.tools or [],
            disallowed_tools=agent.disallowedTools or [],
            output_format=output_format,
        )

        self._emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(
                agent_name=log_name,
                task_id=log_name,
                model=agent.model or "sonnet",
                files_label="",
            ),
        )

        log_file = self._log_path(log_name)
        total_tokens = 0
        tool_calls = 0
        current_tool = ""
        last_result: ResultMessage | None = None
        subagent_tokens: dict[str, int] = {}
        has_subagents = False
        start_time = time.monotonic()

        def _log(entry: dict[str, Any]) -> None:
            if not log_file:
                return
            entry["ts"] = datetime.now(timezone.utc).isoformat()
            with open(log_file, "a") as f:
                f.write(json.dumps(entry, default=repr) + "\n")

        _log(
            {
                "event": "agent_start",
                "name": log_name,
                "description": agent.description,
                "model": agent.model,
                "tools": agent.tools,
                "prompt_length": len(agent.prompt),
                "user_prompt": prompt,
            }
        )

        async def _prompt_gen():
            yield {"type": "user", "message": {"role": "user", "content": prompt}}

        async for message in query(prompt=_prompt_gen(), options=options):
            _log(_serialize_message(message))

            if isinstance(message, AssistantMessage):
                if not has_subagents:
                    usage = message.usage or {}
                    turn_tokens = usage.get("total_tokens", 0) or (
                        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    )
                    total_tokens += turn_tokens

                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name != "Agent":
                        tool_calls += 1
                        current_tool = _tool_detail(block)

                self._emit(
                    EventType.AGENT_PROGRESS,
                    AgentProgressPayload(
                        agent_name=log_name,
                        task_id=log_name,
                        tokens=total_tokens,
                        tool_calls=tool_calls,
                        current_tool=current_tool,
                    ),
                )

            elif isinstance(message, TaskStartedMessage):
                has_subagents = True
                subagent_tokens[message.task_id] = 0

            elif isinstance(message, TaskProgressMessage):
                usage = message.usage
                tokens = (
                    usage["total_tokens"]
                    if isinstance(usage, dict)
                    else getattr(usage, "total_tokens", 0)
                )
                subagent_tokens[message.task_id] = tokens
                total_tokens = sum(subagent_tokens.values())
                tools = (
                    usage.get("tool_uses", 0)
                    if isinstance(usage, dict)
                    else getattr(usage, "tool_uses", 0)
                )
                self._emit(
                    EventType.AGENT_PROGRESS,
                    AgentProgressPayload(
                        agent_name=log_name,
                        task_id=log_name,
                        tokens=total_tokens,
                        tool_calls=tools,
                        current_tool="",
                    ),
                )

            elif isinstance(message, TaskNotificationMessage):
                usage = message.usage
                if usage:
                    final = (
                        usage["total_tokens"]
                        if isinstance(usage, dict)
                        else getattr(usage, "total_tokens", 0)
                    )
                    subagent_tokens[message.task_id] = final
                    total_tokens = sum(subagent_tokens.values())

            elif isinstance(message, ResultMessage):
                last_result = message
                usage = message.usage or {}
                total_tokens = usage.get("total_tokens", 0) or (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Extract structured output
        structured: dict[str, Any] | None = None
        if last_result:
            raw = getattr(last_result, "structured_output", None)
            if raw is not None:
                if isinstance(raw, str):
                    try:
                        structured = json.loads(raw)
                    except json.JSONDecodeError:
                        structured = None
                elif isinstance(raw, dict):
                    structured = raw

        result = RunResult(
            text=getattr(last_result, "result", "") or "" if last_result else "",
            structured=structured,
            usage=last_result.usage or {} if last_result else {},
            cost=getattr(last_result, "total_cost_usd", None) if last_result else None,
            duration_ms=getattr(last_result, "duration_ms", elapsed_ms)
            if last_result
            else elapsed_ms,
        )

        self._emit(
            EventType.AGENT_COMPLETED,
            AgentCompletedPayload(
                agent_name=log_name,
                task_id=log_name,
                tokens=total_tokens,
            ),
        )

        # Write debug markdown
        if log_file:
            structured_out = ""
            if structured:
                structured_out = json.dumps(structured, indent=2, default=repr)
            elif result.text:
                structured_out = result.text

            debug_path = log_file.with_suffix(".md")
            with open(debug_path, "w") as f:
                f.write(f"# Agent: {log_name}\n\n")
                f.write(f"**Model:** {agent.model or 'sonnet'}\n")
                f.write(f"**Tools:** {', '.join(agent.tools or [])}\n\n")
                f.write("## System Prompt\n\n```\n")
                f.write(agent.prompt)
                f.write("\n```\n\n## User Prompt\n\n```\n")
                f.write(prompt)
                f.write("\n```\n\n## Structured Output\n\n```json\n")
                f.write(structured_out or "(no output)")
                f.write("\n```\n")

        return result
