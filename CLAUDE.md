# Codemonkeys

Claude Code plugin providing deterministic, skill-driven workflows for Python development. Skills handle judgment work (review, design, architecture); hooks handle mechanical work (linting, formatting, testing, safety checks).

## Why This Exists

AI-assisted development works best when deterministic tasks run automatically so Claude can focus on decisions that require judgment. Hooks enforce safety and quality without consuming instruction budget; skills coordinate multi-step workflows with hard approval gates.

## Project Structure

```
codemonkeys-plugin/         # The Claude Code plugin
  hooks/                    # Python scripts triggered by Claude Code events
  skills/                   # Slash-command workflows (/codemonkeys:*)
  agents/                   # Subagents dispatched by skills
  shared/                   # Shared guidelines referenced by skills/agents
sandbox.py                  # Standalone OS-level filesystem sandbox
tests/hooks/                # Hook unit tests (subprocess-based)
.codemonkeys/               # Runtime artifacts (gitignored, never committed)
docs/plans/                 # Approved feature plans (committed)
```

## How to Work Here

**Run tests:**
```
pytest tests/
```

**Run a single hook manually** (hooks read JSON from stdin):
```
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"."}' | python codemonkeys-plugin/hooks/pre_tool_use.py
```

**Lint/format** (hooks auto-run ruff on every Python edit, but to run manually):
```
ruff check --fix . && ruff format .
```

**Type check:**
```
pyright .
```

## Architecture Decisions

- **Hooks are deterministic.** No LLM judgment — just tool execution, JSON in/out. Keep them simple and fast.
- **Skills coordinate, agents implement.** `python-feature` designs and gets approval; `python-implementer` writes code via TDD. The plan file is the contract between them.
- **Hard gates before action.** `python-feature` does not dispatch the implementer until the user explicitly approves the plan. The `stop` hook blocks session completion if tests fail.
- **Transient state goes to `.codemonkeys/`.** Check results, logs, attempt counters — all gitignored, cleaned up by `session_start`.

## Detailed Docs (Read When Relevant)

- `codemonkeys-plugin/shared/engineering-mindset.md` — core philosophy: simplicity, correctness, fail-loud boundaries
- `codemonkeys-plugin/shared/python-guidelines.md` — Python conventions: type hints, dataclasses, pure functions, pathlib
- `codemonkeys-plugin/skills/*/SKILL.md` — full skill specifications
- `codemonkeys-plugin/agents/python-implementer.md` — TDD agent spec
- `README.md` — installation, usage, hook reference
