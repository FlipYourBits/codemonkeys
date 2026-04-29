# codemonkeys

## Environment

- Python: `.venv/bin/python`
- Run tests: `.venv/bin/python -m pytest tests/ -x -q --no-header`

## Architecture

- Live by occam's razor — the simplest solution is usually the best. A junior dev should look at this code and immediately understand how it works and how to extend it.
- Each agent has a single responsibility and never depends on another agent.
- Agents are `AgentDefinition` instances in `codemonkeys/agents/`. Parameterized agents use a factory function + default constant. Mechanical agents (lint, test, type check, dep audit) are plain constants.
- Coordinators in `codemonkeys/coordinators/` are interactive sessions that dispatch agents. A coordinator is a factory function returning `ClaudeAgentOptions` with agents registered. The coordinator's system prompt encodes workflows (e.g., "implement feature" → plan → approve → implement → verify). Uses `ClaudeSDKClient` for multi-turn conversation.
- Coordinators are composable: a FastAPI coordinator extends the Python coordinator with additional prompt and agents.
- `codemonkeys/runner.py` provides `AgentRunner` for running individual agents with a Rich live display.
- Structured output uses Pydantic models + `output_format` on `ClaudeAgentOptions`. This only works at the top-level `query()` call, not on subagents dispatched by a coordinator.
- `codemonkeys/prompts/` holds reusable prompt fragments as string constants (e.g., `PYTHON_GUIDELINES`, `PYTHON_SOURCE_FILTER`, `PYTHON_CMD`). Generic instructions that apply across multiple agents belong here — agent-specific logic stays in the agent's own prompt. Agents import and interpolate them via f-string.
- Use `PYTHON_CMD` (`sys.executable`) for agent prompts that reference the Python interpreter. Never hardcode `python` or `.venv/bin/python`.

## Code guidelines

- Use `from __future__ import annotations` in every file.
- Type-hint every public function and method.
- Use `Literal` types for constrained string params (e.g., `scope: Literal["diff", "repo"]`).
- Use Pydantic `BaseModel` for structured data, not dicts.
- Use `pathlib.Path` over `os.path`.
- Use f-strings, not `.format()` or `%`.
- Keep functions short and single-purpose. If a function exceeds ~40 lines, extract a helper.
- Name things for what they mean, not what they are. `parsed_records` over `data`.
- Don't catch `Exception` broadly — catch the narrowest type you can name.
- Don't write defensive code for situations that can't happen given the call graph.
- Don't add comments that restate the code. Comments explain *why*.
- Match the existing codebase style over personal preferences.
- Prefer pure functions. Side effects belong at the edges.
- No dead code, no commented-out blocks, no `# TODO` without a concrete plan.
