"""Agent runner — thin wrapper around claude_agent_sdk.query()."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    ToolUseBlock,
    query,
)

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    EventHandler,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.hooks import build_tool_hooks
from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage

_log = logging.getLogger(__name__)


def _emit(on_event: EventHandler | None, event: Any) -> None:
    if on_event:
        on_event(event)


def _extract_simple_tools(tools: list[str]) -> list[str]:
    """Get tool names suitable for SDK allowed_tools (no Bash patterns)."""
    result = []
    for t in tools:
        if re.match(r"^Bash\(.+\)$", t):
            if "Bash" not in result:
                result.append("Bash")
        else:
            result.append(t)
    return result


async def run_agent(
    agent: AgentDefinition,
    prompt: str,
    on_event: EventHandler | None = None,
) -> RunResult:
    """Run a single agent and return its result."""
    now = time.time()
    _emit(on_event, AgentStarted(agent_name=agent.name, timestamp=now, model=agent.model))

    start_time = time.monotonic()

    # Build output_format from Pydantic schema
    output_format: dict[str, Any] | None = None
    if agent.output_schema:
        output_format = {
            "type": "json_schema",
            "schema": agent.output_schema.model_json_schema(),
        }

    # Build on_deny callback
    def _on_deny(tool_name: str, command: str) -> None:
        _emit(
            on_event,
            ToolDenied(
                agent_name=agent.name,
                timestamp=time.time(),
                tool_name=tool_name,
                command=command,
            ),
        )

    # Build SDK options
    sdk_tools = _extract_simple_tools(agent.tools)
    options = ClaudeAgentOptions(
        system_prompt=agent.system_prompt,
        model=agent.model,
        permission_mode="bypassPermissions",
        allowed_tools=sdk_tools,
        hooks=build_tool_hooks(agent.tools, on_deny=_on_deny),
        output_format=output_format,
    )

    # Track state
    last_result: ResultMessage | None = None
    current_usage = TokenUsage(input_tokens=0, output_tokens=0)
    current_cost = 0.0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            usage = message.usage or {}
            current_usage = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            )

            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    _emit(
                        on_event,
                        ToolCall(
                            agent_name=agent.name,
                            timestamp=time.time(),
                            tool_name=block.name,
                            tool_input=block.input or {},
                        ),
                    )

            _emit(
                on_event,
                TokenUpdate(
                    agent_name=agent.name,
                    timestamp=time.time(),
                    usage=current_usage,
                    cost_usd=current_cost,
                ),
            )

        elif isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            if info.status == "rejected":
                resets_at = info.resets_at or 0
                wait = max(resets_at - int(time.time()), 30)
                _log.warning("Rate limited (%s), waiting %ds", info.rate_limit_type, wait)
                await asyncio.sleep(wait)

        elif isinstance(message, ResultMessage):
            last_result = message

    # Build final result
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if last_result is None:
        error_result = RunResult(
            output=None,
            text="",
            usage=current_usage,
            cost_usd=0.0,
            duration_ms=elapsed_ms,
            error="No result message received from SDK",
        )
        _emit(on_event, AgentError(agent_name=agent.name, timestamp=time.time(), error=error_result.error))
        return error_result

    # Extract from final result
    final_usage_raw = last_result.usage or {}
    final_usage = TokenUsage(
        input_tokens=final_usage_raw.get("input_tokens", 0),
        output_tokens=final_usage_raw.get("output_tokens", 0),
        cache_read_tokens=final_usage_raw.get("cache_read_input_tokens", 0),
        cache_creation_tokens=final_usage_raw.get("cache_creation_input_tokens", 0),
    )
    final_cost = last_result.total_cost_usd or 0.0

    # Parse structured output
    parsed_output = None
    if agent.output_schema and last_result.structured_output is not None:
        raw = last_result.structured_output
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            parsed_output = agent.output_schema.model_validate(raw)

    # Check for error
    error = None
    if last_result.is_error:
        error = last_result.result or "Agent returned an error"

    result = RunResult(
        output=parsed_output,
        text=last_result.result or "",
        usage=final_usage,
        cost_usd=final_cost,
        duration_ms=last_result.duration_ms or elapsed_ms,
        error=error,
    )

    if error:
        _emit(on_event, AgentError(agent_name=agent.name, timestamp=time.time(), error=error))
    else:
        _emit(on_event, AgentCompleted(agent_name=agent.name, timestamp=time.time(), result=result))

    return result
