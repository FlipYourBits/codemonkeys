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
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)

from codemonkeys.core.events import (
    AgentCompleted,
    AgentError,
    AgentStarted,
    EventCollector,
    EventHandler,
    RateLimitHit,
    RawMessage,
    TextOutput,
    ThinkingOutput,
    ToolCall,
    ToolDenied,
    TokenUpdate,
)
from codemonkeys.core.hooks import build_tool_hooks
from codemonkeys.core.types import AgentDefinition, RunResult, TokenUsage, json_safe

_log = logging.getLogger(__name__)

_PRICING: dict[str, dict[str, float]] = {
    "opus": {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_creation": 6.25},
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_creation": 1.25},
}


def _estimate_cost(usage: dict[str, int], model: str) -> float:
    rates = _PRICING.get(model, _PRICING["sonnet"])
    m = 1_000_000
    return (
        usage.get("input_tokens", 0) * rates["input"] / m
        + usage.get("output_tokens", 0) * rates["output"] / m
        + usage.get("cache_read_input_tokens", 0) * rates["cache_read"] / m
        + usage.get("cache_creation_input_tokens", 0) * rates["cache_creation"] / m
    )


_json_safe = json_safe


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
    collector = EventCollector()

    def _combined_emit(event: Any) -> None:
        collector.handle(event)
        if on_event:
            on_event(event)

    now = time.time()
    _combined_emit(AgentStarted(agent_name=agent.name, timestamp=now, model=agent.model))

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
        _combined_emit(
            ToolDenied(
                agent_name=agent.name,
                timestamp=time.time(),
                tool_name=tool_name,
                command=command,
            ),
        )

    # Build SDK options — restrict to declared tools only, no external extensions
    sdk_tools = _extract_simple_tools(agent.tools)
    options = ClaudeAgentOptions(
        system_prompt=agent.system_prompt,
        model=agent.model,
        permission_mode="bypassPermissions",
        tools=sdk_tools,
        allowed_tools=sdk_tools,
        hooks=build_tool_hooks(agent.tools, on_deny=_on_deny),
        output_format=output_format,
        mcp_servers={},
        plugins=[],
        setting_sources=[],
        skills=[],
    )

    # Track state
    last_result: ResultMessage | None = None
    current_usage = TokenUsage(input_tokens=0, output_tokens=0)
    current_cost = 0.0
    last_emitted_usage: TokenUsage | None = None

    async for message in query(prompt=prompt, options=options):
        # Emit raw message for full-fidelity logging
        _combined_emit(
            RawMessage(
                agent_name=agent.name,
                timestamp=time.time(),
                message_type=type(message).__name__,
                data=_json_safe(message),
            ),
        )

        if isinstance(message, AssistantMessage):
            usage = message.usage or {}
            current_usage = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            )
            current_cost = _estimate_cost(usage, agent.model)

            for block in message.content:
                if isinstance(block, ThinkingBlock):
                    _combined_emit(
                        ThinkingOutput(
                            agent_name=agent.name,
                            timestamp=time.time(),
                            text=block.thinking or "",
                        ),
                    )
                elif isinstance(block, TextBlock):
                    _combined_emit(
                        TextOutput(
                            agent_name=agent.name,
                            timestamp=time.time(),
                            text=block.text or "",
                        ),
                    )
                elif isinstance(block, ToolUseBlock):
                    _combined_emit(
                        ToolCall(
                            agent_name=agent.name,
                            timestamp=time.time(),
                            tool_name=block.name,
                            tool_input=block.input or {},
                        ),
                    )

            if current_usage != last_emitted_usage:
                _combined_emit(
                    TokenUpdate(
                        agent_name=agent.name,
                        timestamp=time.time(),
                        usage=current_usage,
                        cost_usd=current_cost,
                    ),
                )
                last_emitted_usage = current_usage

        elif isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            resets_at = info.resets_at or 0
            wait = (
                max(resets_at - int(time.time()), 30)
                if info.status == "rejected"
                else 0
            )
            _combined_emit(
                RateLimitHit(
                    agent_name=agent.name,
                    timestamp=time.time(),
                    rate_limit_type=info.rate_limit_type or "unknown",
                    status=info.status,
                    wait_seconds=wait,
                ),
            )
            if info.status == "rejected":
                _log.warning(
                    "Rate limited (%s), waiting %ds", info.rate_limit_type, wait
                )
                await asyncio.sleep(wait)

        elif isinstance(message, ResultMessage):
            last_result = message

    # Build final result
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if last_result is None:
        err_msg = "No result message received from SDK"
        error_result = RunResult(
            output=None,
            text="",
            usage=current_usage,
            cost_usd=0.0,
            duration_ms=elapsed_ms,
            error=err_msg,
            agent_def=agent,
            events=list(collector.events),
        )
        _combined_emit(
            AgentError(agent_name=agent.name, timestamp=time.time(), error=err_msg),
        )
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

    # Snapshot events before emitting the terminal event — otherwise
    # AgentCompleted.result.events would contain itself (circular ref).
    events_snapshot = list(collector.events)

    result = RunResult(
        output=parsed_output,
        text=last_result.result or "",
        usage=final_usage,
        cost_usd=final_cost,
        duration_ms=last_result.duration_ms or elapsed_ms,
        error=error,
        agent_def=agent,
        events=events_snapshot,
    )

    if error:
        _combined_emit(
            AgentError(agent_name=agent.name, timestamp=time.time(), error=error),
        )
    else:
        _combined_emit(
            AgentCompleted(agent_name=agent.name, timestamp=time.time(), result=result),
        )

    return result
