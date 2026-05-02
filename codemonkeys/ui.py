"""Shared UI components for agent display."""

from __future__ import annotations

from dataclasses import dataclass

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def format_elapsed(secs: float) -> str:
    if secs < 60:
        return f"{secs:.1f}s"
    m, s = divmod(int(secs), 60)
    return f"{m}m {s:02d}s"


def summarize_tool(name: str, inp: dict[str, object]) -> str:
    """Format tool name + key argument for display."""
    if name in ("Read", "Edit", "Write"):
        path = str(inp.get("file_path", ""))
        if path:
            return f"{name}({path})"
    elif name == "Glob":
        return f"Glob({inp.get('pattern', '')})"
    elif name == "Grep":
        return f"Grep({inp.get('pattern', inp.get('query', ''))})"
    elif name == "Bash":
        cmd = str(inp.get("command", ""))
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"Bash({cmd})"
    return name


@dataclass(slots=True)
class AgentState:
    """Tracks state for one agent in the table."""

    name: str
    started: float
    tokens: int = 0
    last_tool: str = ""
    status: str = "running"
    end_time: float | None = None


def render_agent_table(
    agents: dict[str, AgentState],
    now: float,
    spinner_idx: int,
    cols: int = 80,
) -> str:
    """Render a box-drawing agent table. Returns a multi-line string."""
    if not agents:
        return ""

    name_w = max(len(a.name) for a in agents.values()) + 1
    name_w = max(name_w, 8)
    time_w = 6
    tok_w = 7
    act_w = max(20, cols - name_w - time_w - tok_w - 5)

    def hl(left: str, mid: str, right: str) -> str:
        return f"{left}{'─' * name_w}{mid}{'─' * time_w}{mid}{'─' * tok_w}{mid}{'─' * act_w}{right}"

    lines = [
        hl("┌", "┬", "┐"),
        f"│{'Agent':^{name_w}}│{'Time':^{time_w}}│{'Tok':^{tok_w}}│{'Activity':^{act_w}}│",
        hl("├", "┼", "┤"),
    ]
    for agent in agents.values():
        if agent.end_time:
            elapsed = format_elapsed(agent.end_time - agent.started)
        else:
            elapsed = format_elapsed(now - agent.started)
        tok_str = (
            f"{agent.tokens // 1000}k" if agent.tokens >= 1000 else str(agent.tokens)
        )
        if agent.status == "complete":
            activity = "✓ done"
        elif agent.last_tool:
            sp = SPINNER[spinner_idx % len(SPINNER)]
            activity = f"{sp} {agent.last_tool}"
            if len(activity) > act_w - 1:
                activity = activity[: act_w - 2] + "…"
        else:
            sp = SPINNER[spinner_idx % len(SPINNER)]
            activity = f"{sp} starting..."
        lines.append(
            f"│{agent.name:<{name_w}}│{elapsed:>{time_w}}│{tok_str:>{tok_w}}│ {activity:<{act_w - 1}}│"
        )
    lines.append(hl("└", "┴", "┘"))
    return "\n".join(lines)
