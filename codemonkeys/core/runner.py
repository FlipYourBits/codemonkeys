"""Reusable agent runner with event emission, debug logging, and filesystem sandboxing."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)

_log = logging.getLogger(__name__)

from codemonkeys.core._runner_helpers import (
    _build_tool_hooks,
    _estimate_cost,
    _serialize_message,
    _tool_detail,
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
        agent_name: str | None = None,  # backward-compat alias for log_name
        files: str = "",
        on_tool_call: Any | None = None,
        on_event: Any | None = None,
    ) -> RunResult:
        # agent_name was the original parameter name; accept both for backwards compat
        if agent_name is not None:
            log_name = agent_name

        restrict(self.cwd)

        log_label = f"{log_name}__{files}" if files else log_name
        log_file = self._log_path(log_label)
        total_tokens = 0
        total_cost = 0.0
        tool_calls = 0
        current_tool = ""
        last_result: ResultMessage | None = None
        subagent_tokens: dict[str, int] = {}
        has_subagents = False
        start_time = time.monotonic()

        def _write_log(entry: dict[str, Any]) -> None:
            if not log_file:
                return
            entry["ts"] = datetime.now(timezone.utc).isoformat()
            with open(log_file, "a") as f:
                f.write(json.dumps(entry, default=repr) + "\n")

        def _on_tool_denied(command: str, patterns: list[str]) -> None:
            _write_log(
                {
                    "event": "tool_denied",
                    "tool": "Bash",
                    "command": command,
                    "permitted_patterns": patterns,
                }
            )
            if on_tool_call:
                nonlocal tool_calls
                tool_calls += 1
                on_tool_call(
                    tool_calls,
                    f"Bash($ {command[:80]})  DENIED",
                    total_tokens,
                    total_cost,
                )

        tools = agent.tools or []
        options = ClaudeAgentOptions(
            system_prompt=agent.prompt,
            model=agent.model or "sonnet",
            cwd=self.cwd,
            permission_mode=agent.permissionMode or "dontAsk",
            allowed_tools=tools,
            disallowed_tools=agent.disallowedTools or [],
            hooks=_build_tool_hooks(tools, on_deny=_on_tool_denied),
            output_format=output_format,
            setting_sources=[],
        )

        self._emit(
            EventType.AGENT_STARTED,
            AgentStartedPayload(
                agent_name=log_name,
                task_id=log_label,
                model=agent.model or "sonnet",
                files_label=files,
            ),
        )

        _write_log(
            {
                "event": "agent_start",
                "name": log_label,
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
            _write_log(_serialize_message(message))

            if isinstance(message, AssistantMessage):
                if not has_subagents:
                    usage = message.usage or {}
                    total_tokens = usage.get("total_tokens", 0) or (
                        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    )
                    total_cost = _estimate_cost(usage, agent.model or "sonnet")

                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        if block.name != "Agent":
                            tool_calls += 1
                            current_tool = _tool_detail(block)
                            if on_tool_call:
                                on_tool_call(
                                    tool_calls, current_tool, total_tokens, total_cost
                                )
                        if on_event:
                            on_event(
                                {
                                    "type": "tool_use",
                                    "name": block.name,
                                    "input": block.input,
                                    "detail": _tool_detail(block),
                                }
                            )
                    elif isinstance(block, ThinkingBlock):
                        if on_event:
                            on_event(
                                {"type": "thinking", "content": block.thinking or ""}
                            )
                    elif isinstance(block, TextBlock):
                        if on_event:
                            on_event({"type": "text", "content": block.text or ""})

                self._emit(
                    EventType.AGENT_PROGRESS,
                    AgentProgressPayload(
                        agent_name=log_name,
                        task_id=log_label,
                        tokens=total_tokens,
                        cost=total_cost,
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
                        task_id=log_label,
                        tokens=total_tokens,
                        cost=total_cost,
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

            elif isinstance(message, RateLimitEvent):
                info = message.rate_limit_info
                if on_event:
                    on_event(
                        {
                            "type": "rate_limit",
                            "status": info.status,
                            "rate_limit_type": info.rate_limit_type,
                        }
                    )
                if info.status == "rejected":
                    resets_at = info.resets_at or 0
                    wait = max(resets_at - int(time.time()), 30)
                    _log.warning(
                        "Rate limited (%s), waiting %ds before retry",
                        info.rate_limit_type or "unknown",
                        wait,
                    )
                    if on_event:
                        on_event(
                            {
                                "type": "rate_limit_wait",
                                "wait_seconds": wait,
                                "rate_limit_type": info.rate_limit_type,
                            }
                        )
                    self._emit(
                        EventType.AGENT_PROGRESS,
                        AgentProgressPayload(
                            agent_name=log_name,
                            task_id=log_label,
                            tokens=total_tokens,
                            cost=total_cost,
                            tool_calls=tool_calls,
                            current_tool=f"rate limited — retrying in {wait}s",
                        ),
                    )
                    await asyncio.sleep(wait)

            elif isinstance(message, ResultMessage):
                last_result = message
                usage = message.usage or {}
                total_tokens = usage.get("total_tokens", 0) or (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )
                if on_event:
                    on_event(
                        {
                            "type": "result",
                            "tokens": total_tokens,
                            "cost": getattr(message, "total_cost_usd", None),
                            "duration_ms": getattr(message, "duration_ms", 0),
                        }
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
                task_id=log_label,
                tokens=total_tokens,
                cost=total_cost,
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
