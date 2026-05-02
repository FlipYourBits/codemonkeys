# codemonkeys

AI agent workflows powered by the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

Agents do one thing. Coordinators orchestrate them.

## Why not just use Claude Code?

Claude Code is a general-purpose coding assistant. codemonkeys builds specialized, composable agents with controls that CC doesn't offer:

- **Per-agent permission control.** CC is one permission mode for the whole session. Here, the coordinator is interactive but its subagents run `dontAsk` — the reviewer is read-only (zero prompts), the fixer writes files silently. You control exactly where the human decision point is.
- **Right-sized models.** CC uses one model for everything. codemonkeys assigns haiku to mechanical tasks (run ruff, run pytest), sonnet to judgment calls (docs review, coordination), and opus to deep analysis (security audit, code review, implementation). Same quality, fraction of the cost.
- **Composable coordinators.** A Python coordinator has Python agents. A FastAPI coordinator extends it with FastAPI knowledge. A full-stack coordinator combines Python and JavaScript. Stack expertise like building blocks.
- **Deterministic workflows.** The coordinator follows structured workflows: plan → approve → implement → verify. No guessing, no skipped steps. The workflow is encoded in the prompt, enforced by agent constraints.
- **Structured output.** Review agents return typed findings (file, line, severity, category) that downstream agents can act on programmatically.
- **Unattended agents.** Subagents run `dontAsk` with constrained tools. The coordinator handles all user interaction — subagents just execute.

## Prerequisites

- Python 3.10 or newer
- `ANTHROPIC_API_KEY` environment variable set
- Optional: Linux kernel 5.13+ for full Landlock sandbox support

## Install

```bash
git clone https://github.com/FlipYourBits/codemonkeys.git
cd codemonkeys
pip install -e ".[dev]"
```

The `[dev]` extras are required to run the built-in Python toolchain agents (linter, type checker, test runner, dependency auditor). Installing without them will cause runtime failures when those agents try to invoke `ruff`, `pytest`, `mypy`, or `pip-audit`.

Requires Python 3.10+ and a Claude API key (`ANTHROPIC_API_KEY`).

## Quick Start

```bash
# Start an interactive Python coordinator session
.venv/bin/python -m codemonkeys.coordinators.python

# With an initial prompt
.venv/bin/python -m codemonkeys.coordinators.python "review the code"

# With a specific working directory
.venv/bin/python -m codemonkeys.coordinators.python --cwd /path/to/project

# Auto-generate or update docs/codemonkeys/architecture.md before each session
.venv/bin/python -m codemonkeys.coordinators.python --use-project-memory
```

The coordinator is an interactive session — you chat with it, it dispatches agents.

## Project Structure

```
codemonkeys/
  agents/           # Individual agent definitions (AgentDefinition instances)
  coordinators/     # Interactive sessions that dispatch agents
  prompts/          # Shared prompt fragments used across agents
  runner.py         # AgentRunner — runs individual agents with a Rich live display
  shell.py          # AppShell — reusable full-screen TUI for coordinators
  ui.py             # AgentState dataclass and shared display helpers
  sandbox.py        # OS-level filesystem write restriction (restrict())
  schemas.py        # JSON output schema constants for structured agent output
```

### Agents

Each file in `agents/` exports a factory function that returns an `AgentDefinition` — a self-contained agent with a prompt, model, tool permissions, and scope. Agents are stateless workers that do one focused job.

#### Reviewers (read-only, safe to run in parallel)

| Factory | Model | What it does |
|---------|-------|-------------|
| `make_python_type_checker` | haiku | Runs mypy, returns type errors |
| `make_python_test_runner` | haiku | Runs pytest, returns results |
| `make_python_coverage_analyzer` | haiku | Runs pytest --cov, returns uncovered lines |
| `make_python_dep_auditor` | haiku | Runs pip-audit, returns vulnerabilities |
| `make_python_quality_reviewer` | opus | Clean code review — naming, design, patterns, complexity |
| `make_python_security_auditor` | opus | Security vulnerabilities — injection, secrets, auth |
| `make_readme_reviewer` | sonnet | README accuracy, completeness, stale references |
| `make_changelog_reviewer` | sonnet | CHANGELOG.md completeness against git history |
| `make_definition_reviewer` | opus | Reviews AgentDefinition files for correctness |

#### Writers (edit files, run sequentially after user approval)

| Factory | Model | What it does |
|---------|-------|-------------|
| `make_python_linter` | haiku | Runs ruff check --fix + ruff format |
| `make_python_fixer` | opus | Applies targeted fixes for findings from reviewers |
| `make_python_test_writer` | opus | Writes tests for uncovered code from coverage reports |
| `make_python_implementer` | opus | Implements features from an approved plan |

#### Memory

| Factory | Model | What it does |
|---------|-------|-------------|
| `make_project_memory_agent` | sonnet | Builds or updates `docs/codemonkeys/architecture.md` — full scan in `mode="full"`, incremental diff-based update in `mode="incremental"` |
| `make_project_memory_updater` | sonnet | Self-contained variant: checks `.memory-hash` against `HEAD` and rebuilds or updates only if stale. Safe to dispatch on startup |

### Coordinators

A coordinator is an interactive Claude session with constrained subagents. You chat with the coordinator; it reads code, plans, dispatches agents, and reports back.

**Python Coordinator** — full Python development assistant with agents for linting, testing, type checking, code review, security audit, and implementation.

Built-in workflows:
- **Implement a feature** → plan → present → approve → dispatch implementer → verify
- **Quality check** → lint → type check → test → code review → security audit → present findings → fix
- **Code review** → dispatch reviewers → present findings → fix selected issues
- **Write tests** → run coverage → write tests for uncovered code → verify

### Composing Coordinators

Coordinators are composable — extend a base coordinator with additional expertise:

```python
from claude_agent_sdk import ClaudeAgentOptions
from codemonkeys.coordinators.python import python_coordinator, PYTHON_PROMPT
from codemonkeys.agents import make_python_quality_reviewer

def fastapi_coordinator(cwd="."):
    base = python_coordinator(cwd)
    agents = dict(base.agents or {})
    agents["fastapi_quality_reviewer"] = make_python_quality_reviewer(scope="repo")
    return ClaudeAgentOptions(
        system_prompt=PYTHON_PROMPT + FASTAPI_ADDITIONS,
        model="sonnet",
        cwd=cwd,
        permission_mode="acceptEdits",
        allowed_tools=["Read", "Glob", "Grep", "Agent"],
        agents=agents,
    )
```

### Using Agents Directly

Each agent can also be run standalone via its `__main__` block or dispatched programmatically:

```python
from codemonkeys.agents import make_python_quality_reviewer
from codemonkeys.runner import AgentRunner

runner = AgentRunner()

# Run with default scope (diff against main)
result = await runner.run_agent(make_python_quality_reviewer(), "Review the code.")

# Customize scope
reviewer = make_python_quality_reviewer(scope="repo", path="src/")
result = await runner.run_agent(reviewer, "Review src/ for issues.")
```

**Definition Review** — reviews AgentDefinition files for correctness:

```bash
.venv/bin/python -m codemonkeys.agents.review_agent_definition codemonkeys/agents/python_quality_reviewer.py
```

## Model Configuration

Agents use model aliases (`"haiku"`, `"sonnet"`, `"opus"`) instead of full model IDs. The CLI resolves these to the correct model for your provider (Anthropic API, Bedrock, or Vertex).

By default, aliases resolve to the latest version of each model. To pin specific versions (recommended for Bedrock/Vertex), set environment variables:

```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL='us.anthropic.claude-opus-4-7'
export ANTHROPIC_DEFAULT_SONNET_MODEL='us.anthropic.claude-sonnet-4-6'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='us.anthropic.claude-haiku-4-5'
```

> **Note:** these are Claude CLI / Anthropic SDK environment variables. Verify the variable names against your installed Claude CLI version — naming has changed across releases.

## Writing New Agents

Create a file in `codemonkeys/agents/` with a constant or factory:

```python
from __future__ import annotations
from claude_agent_sdk import AgentDefinition

MY_AGENT = AgentDefinition(
    description="Use this agent to ...",  # coordinator sees this
    prompt="...",                          # agent's full instructions
    model="haiku",                        # model alias
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Bash(git push*)", "Bash(git commit*)"],
    permissionMode="dontAsk",
)
```

For parameterized agents, use a factory function. See existing agents for the pattern.

See [docs/agent-definition.md](docs/agent-definition.md) for a full reference of all parameters.

## Sandbox

Agents run inside an OS-level filesystem sandbox that restricts writes to the project directory. Call `restrict()` once at startup — all child processes (including SDK-spawned agents) inherit the restriction.

```python
from codemonkeys.sandbox import restrict

restrict("/path/to/project")
# From here, writes outside the project directory are denied by the kernel.
```

| Platform | Mechanism | Dependency |
|----------|-----------|------------|
| Linux | Landlock LSM (kernel 5.13+) | `landlock` (pure Python) |
| macOS | sandbox-exec / Seatbelt | none |
| Windows | Low Integrity Token | none |

`AgentRunner` and the built-in Python coordinator call `restrict()` automatically. If you build a custom coordinator that uses `ClaudeSDKClient` directly (or any other entry point that doesn't go through `AgentRunner`), you must call `codemonkeys.sandbox.restrict(cwd)` yourself before any agent dispatch.

## Tests

```bash
.venv/bin/python -m pytest tests/ -x -q --no-header
```

## Docs

- [AgentDefinition Parameters](docs/agent-definition.md) — full reference for all agent configuration options
- [Changelog](CHANGELOG.md)

## Contributing

```bash
git clone https://github.com/FlipYourBits/codemonkeys.git
cd codemonkeys
pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -x -q --no-header
```

Open a GitHub issue for bug reports and feature requests.

## License

MIT — see [LICENSE](LICENSE).
