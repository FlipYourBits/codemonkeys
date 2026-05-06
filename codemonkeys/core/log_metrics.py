"""Extract structured metrics from agent JSONL log files."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ToolCall:
    turn: int
    name: str
    args_summary: str


@dataclass
class Turn:
    index: int
    role: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    text_content: str = ""


@dataclass
class LogMetrics:
    agent_name: str = ""
    model: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    total_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cost: float = 0.0
    duration_ms: int = 0
    turns: list[Turn] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    repeated_tool_calls: list[ToolCall] = field(default_factory=list)
    unauthorized_tool_calls: list[ToolCall] = field(default_factory=list)
    rate_limit_events: list[dict] = field(default_factory=list)
    structured_output: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


def _summarize_tool_args(name: str, tool_input: dict) -> str:
    if name in ("Read", "Edit", "Write"):
        return tool_input.get("file_path", "?")
    if name == "Grep":
        return tool_input.get("pattern", "?")
    if name == "Glob":
        return tool_input.get("pattern", tool_input.get("path", "?"))
    if name == "Bash":
        return tool_input.get("command", "")[:120]
    if name == "StructuredOutput":
        return "(structured output)"
    return str(tool_input)[:120]


def _is_tool_authorized(
    tool_name: str, tool_input: dict, allowed_tools: list[str]
) -> bool:
    for spec in allowed_tools:
        if spec == tool_name:
            return True
        m = re.match(r"^(\w+)\((.+)\)$", spec)
        if m and m.group(1) == tool_name:
            pattern = m.group(2)
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                if fnmatch.fnmatch(command, pattern):
                    return True
    # StructuredOutput is always implicitly allowed (SDK internal)
    if tool_name == "StructuredOutput":
        return True
    return False


def _extract_system_prompt(log_file: Path) -> str:
    md_candidates = list(log_file.parent.glob(log_file.stem.rsplit(".", 1)[0] + "*.md"))
    if not md_candidates:
        md_candidates = list(log_file.parent.glob("*.md"))
    for md_path in md_candidates:
        text = md_path.read_text()
        marker = "## System Prompt\n\n```\n"
        start = text.find(marker)
        if start == -1:
            continue
        start += len(marker)
        end = text.find("\n```\n", start)
        if end == -1:
            continue
        return text[start:end]
    return ""


def extract_metrics(log_file: Path) -> LogMetrics:
    metrics = LogMetrics()
    assistant_turn_index = 0

    lines = log_file.read_text().strip().split("\n")
    for line in lines:
        entry = json.loads(line)

        if entry.get("event") == "agent_start":
            metrics.agent_name = entry.get("name", "")
            metrics.model = entry.get("model", "")
            metrics.allowed_tools = entry.get("tools", [])
            metrics.user_prompt = entry.get("user_prompt", "")
            continue

        if entry.get("event") == "tool_denied":
            tc = ToolCall(
                turn=assistant_turn_index,
                name=entry.get("tool", "Bash"),
                args_summary=entry.get("command", ""),
            )
            metrics.unauthorized_tool_calls.append(tc)
            metrics.tool_calls.append(tc)
            continue

        msg_type = entry.get("type", "")

        if msg_type == "RateLimitEvent":
            metrics.rate_limit_events.append(
                {
                    "status": entry.get("status"),
                    "rate_limit_type": entry.get("rate_limit_type"),
                    "resets_at": entry.get("resets_at"),
                    "utilization": entry.get("utilization"),
                }
            )
            continue

        if msg_type == "AssistantMessage":
            assistant_turn_index += 1
            usage = entry.get("usage", {})
            content_blocks = entry.get("content", [])

            thinking_parts = []
            text_parts = []
            turn_tool_calls = []

            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "thinking":
                    thinking_parts.append(block.get("thinking", ""))
                elif block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tc = ToolCall(
                        turn=assistant_turn_index,
                        name=tool_name,
                        args_summary=_summarize_tool_args(tool_name, tool_input),
                    )
                    turn_tool_calls.append(tc)
                    metrics.tool_calls.append(tc)

                    if not _is_tool_authorized(
                        tool_name, tool_input, metrics.allowed_tools
                    ):
                        metrics.unauthorized_tool_calls.append(tc)

            turn = Turn(
                index=assistant_turn_index,
                role="assistant",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                thinking_content="\n".join(thinking_parts),
                tool_calls=turn_tool_calls,
                text_content="\n".join(text_parts),
            )
            metrics.turns.append(turn)
            metrics.total_turns = assistant_turn_index
            continue

        if msg_type == "ResultMessage":
            result_usage = entry.get("usage", {})
            metrics.total_input_tokens = result_usage.get("input_tokens", 0)
            metrics.total_output_tokens = result_usage.get("output_tokens", 0)
            metrics.total_cache_read_tokens = result_usage.get(
                "cache_read_input_tokens", 0
            )
            metrics.total_cache_creation_tokens = result_usage.get(
                "cache_creation_input_tokens", 0
            )
            metrics.total_cost = entry.get("cost", 0.0) or 0.0
            metrics.duration_ms = entry.get("duration_ms", 0)
            metrics.structured_output = entry.get("result")
            continue

    metrics.system_prompt = _extract_system_prompt(log_file)

    # Detect repeated tool calls: same (name, args_summary) appearing more than once
    seen: dict[tuple[str, str], list[ToolCall]] = {}
    for tc in metrics.tool_calls:
        key = (tc.name, tc.args_summary)
        seen.setdefault(key, []).append(tc)
    for key, calls in seen.items():
        if len(calls) > 1:
            metrics.repeated_tool_calls.extend(calls)

    return metrics
