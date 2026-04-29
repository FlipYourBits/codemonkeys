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

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+ and a Claude API key (`ANTHROPIC_API_KEY`).

## Quick Start

```bash
# Start an interactive Python coordinator session
.venv/bin/python -m codemonkeys.coordinators.python

# With an initial prompt
.venv/bin/python -m codemonkeys.coordinators.python "review the code"

# With a specific working directory
.venv/bin/python -m codemonkeys.coordinators.python --cwd /path/to/project
```

The coordinator is an interactive session — you chat with it, it dispatches agents.

## Project Structure

```
codemonkeys/
  agents/           # Individual agent definitions (AgentDefinition instances)
  coordinators/     # Interactive sessions that dispatch agents
  prompts/          # Shared prompt fragments used across agents
```

### Agents

Each file in `agents/` exports a single `AgentDefinition` — a self-contained agent with a prompt, model, tool permissions, and scope. Agents are stateless workers that do one focused job.

| Agent | Model | What it does |
|-------|-------|-------------|
| `LINTER` | haiku | Runs ruff check --fix + ruff format |
| `TYPE_CHECKER` | haiku | Runs mypy, returns type errors |
| `TEST_RUNNER` | haiku | Runs pytest, returns results |
| `DEP_AUDITOR` | haiku | Runs pip-audit, returns vulnerabilities |
| `CODE_REVIEWER` | opus | Static code review — logic errors, resource leaks, dead code, complexity |
| `SECURITY_AUDITOR` | opus | Security vulnerabilities — injection, secrets, unsafe deserialization |
| `DOCS_REVIEWER` | sonnet | Finds documentation drift against code |
| `FIXER` | opus | Applies targeted fixes for findings from any agent |
| `IMPLEMENTER` | opus | Implements features from an approved plan |
| `TEST_WRITER` | opus | Writes tests for uncovered code from coverage reports |
| `DEFINITION_REVIEWER` | opus | Reviews AgentDefinition files for correctness |

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
from codemonkeys.coordinators.python import python_coordinator, PYTHON_AGENTS, PYTHON_PROMPT

def fastapi_coordinator(cwd="."):
    return ClaudeAgentOptions(
        system_prompt=PYTHON_PROMPT + FASTAPI_ADDITIONS,
        model="sonnet",
        cwd=cwd,
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep", "Bash", "Agent"],
        agents={**PYTHON_AGENTS, "api_tester": API_TESTER},
    )
```

### Using Agents Directly

Each agent can also be run standalone via its `__main__` block or dispatched programmatically:

```python
from codemonkeys.agents import CODE_REVIEWER, make_code_reviewer
from codemonkeys.runner import AgentRunner

runner = AgentRunner()

# Run with default scope (diff against main)
result = await runner.run_agent(CODE_REVIEWER, "Review the code.")

# Use a factory to customize scope
reviewer = make_code_reviewer(scope="repo", path="src/")
result = await runner.run_agent(reviewer, "Review src/ for issues.")
```

**Definition Review** — reviews AgentDefinition files for correctness and optionally fixes issues:

```bash
.venv/bin/python -m codemonkeys.agents.review_agent_definition codemonkeys/agents/python_code_review.py
```

## Model Configuration

Agents use model aliases (`"haiku"`, `"sonnet"`, `"opus"`) instead of full model IDs. The CLI resolves these to the correct model for your provider (Anthropic API, Bedrock, or Vertex).

By default, aliases resolve to the latest version of each model. To pin specific versions (recommended for Bedrock/Vertex), set environment variables:

```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL='us.anthropic.claude-opus-4-7'
export ANTHROPIC_DEFAULT_SONNET_MODEL='us.anthropic.claude-sonnet-4-6'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='us.anthropic.claude-haiku-4-5'
```

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

For parameterized agents, use a factory function + default constant. See existing agents for the pattern.

See [docs/agent-definition.md](docs/agent-definition.md) for a full reference of all parameters.

## Tests

```bash
.venv/bin/python -m pytest tests/ -x -q --no-header
```

## Docs

- [AgentDefinition Parameters](docs/agent-definition.md) — full reference for all agent configuration options
