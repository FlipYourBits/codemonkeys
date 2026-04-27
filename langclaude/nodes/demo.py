"""Demo node: simulates Claude-like work with fake delays and JSON output.

No LLM calls — just sleeps and returns canned results. Useful for testing
the Display and Pipeline without spending tokens.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Callable
from typing import Any

from claude_agent_sdk import AssistantMessage, TextBlock

from langclaude.nodes.base import Verbosity

_TOOL_CALLS = [
    "→ Read(src/main.py)",
    "→ Grep(pattern='TODO', include='*.py')",
    "→ Bash(git diff --stat)",
    "→ Read(tests/test_main.py)",
    "→ Edit(src/utils.py)",
    "→ Bash(python -m pytest tests/ -x -q)",
    "→ Read(pyproject.toml)",
    "→ Grep(pattern='import', include='*.py')",
    "(thinking…)",
    "→ Bash(git log --oneline -5)",
]


def _fake_message(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text)], model="demo")


def demo_node(
    *,
    name: str = "demo",
    output: dict[str, Any] | None = None,
    delay: float = 1.5,
    steps: int = 6,
    cost: float = 0.0,
    verbosity: Verbosity = Verbosity.silent,
) -> Callable[[dict[str, Any]], Any]:
    async def run(state: dict[str, Any]) -> dict[str, Any]:
        on_message = getattr(run, "on_message", None)
        per_step = delay / max(steps, 1)
        calls = random.sample(_TOOL_CALLS, min(steps, len(_TOOL_CALLS)))

        for call in calls:
            if on_message is not None:
                on_message(name, _fake_message(call))
            await asyncio.sleep(per_step)

        result = output if output is not None else {"status": "ok", "node": name}
        return {name: json.dumps(result), "last_cost_usd": cost}

    run.__name__ = name
    run.on_message = None  # type: ignore[attr-defined]
    run.declared_outputs = (name, "last_cost_usd")  # type: ignore[attr-defined]
    return run
