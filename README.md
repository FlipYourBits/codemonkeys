# codemonkeys

AI agent workflows powered by the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

Agents do one thing. Coordinators orchestrate them.

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+ and a Claude API key (`ANTHROPIC_API_KEY`).

## Project Structure

```
codemonkeys/
  agents/           # Individual agent definitions (AgentDefinition instances)
  coordinators/     # Orchestrate agents into workflows
  skills/           # Shared prompt text constants used by agents
```

### Agents

Each file in `agents/` exports a single `AgentDefinition` — a self-contained agent with a prompt, model, tool permissions, and scope. Agents are stateless workers that do one focused job.

| Agent | What it does |
|-------|-------------|
| `CODE_REVIEWER` | Static code review — logic errors, resource leaks, dead code, complexity |
| `SECURITY_AUDITOR` | Security vulnerabilities — injection, secrets, unsafe deserialization |
| `TEST_RUNNER` | Runs pytest and analyzes failures |
| `TYPE_CHECKER` | Runs mypy and reports type errors |
| `LINTER` | Runs ruff and reports lint violations |
| `DEPENDENCY_AUDITOR` | Scans for known CVEs via pip-audit |
| `DOCS_REVIEWER` | Finds documentation drift against code |
| `FIXER` | Applies targeted fixes for findings from review agents |
| `PROMPT_REVIEWER` | Evaluates agent prompts for comprehensiveness |

### Coordinators

Coordinators dispatch agents and combine their results. Each coordinator is a workflow.

**Review Coordinator** — Dispatches all review agents in parallel, collects findings, and optionally dispatches the fixer.

```bash
# Run a full code review
.venv/bin/python -m codemonkeys.coordinators.review /path/to/repo

# Review without fix prompt
.venv/bin/python -m codemonkeys.coordinators.review . --no-fix

# Review a single file
.venv/bin/python -m codemonkeys.coordinators.review . --file src/main.py

# Save results to JSON
.venv/bin/python -m codemonkeys.coordinators.review . -o results.json
```

**Prompt Review Coordinator** — Reviews an agent prompt file for gaps and optionally rewrites it.

```bash
.venv/bin/python -m codemonkeys.coordinators.prompt_review codemonkeys/agents/python_code_review.py
```

### Using Agents in Your Own Code

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from codemonkeys.agents import CODE_REVIEWER, TEST_RUNNER, FIXER

options = ClaudeAgentOptions(
    system_prompt="You are a coordinator. Dispatch review agents and combine findings.",
    model="sonnet",
    cwd=".",
    permission_mode="bypassPermissions",
    allowed_tools=["Agent"],
    agents={
        "code_reviewer": CODE_REVIEWER,
        "test_runner": TEST_RUNNER,
        "fixer": FIXER,
    },
)
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

Create a file in `codemonkeys/agents/` that exports an `AgentDefinition`:

```python
from claude_agent_sdk import AgentDefinition

MY_AGENT = AgentDefinition(
    description="Use this agent to ...",  # coordinator sees this to decide dispatch
    prompt="...",                          # the agent's full instructions
    model="haiku",                         # model alias
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Edit", "Write"],
    permissionMode="bypassPermissions",
)
```

See [docs/agent-definition.md](docs/agent-definition.md) for a full reference of all parameters.

## Writing New Coordinators

Create a file in `codemonkeys/coordinators/` that uses `ClaudeAgentOptions` with your agents:

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from codemonkeys.agents import CODE_REVIEWER, TEST_RUNNER

options = ClaudeAgentOptions(
    system_prompt="Dispatch all agents and combine findings.",
    model="sonnet",
    cwd=working_dir,
    permission_mode="bypassPermissions",
    allowed_tools=["Agent"],
    agents={
        "code_reviewer": CODE_REVIEWER,
        "test_runner": TEST_RUNNER,
    },
)

async for message in query(prompt=..., options=options):
    # handle messages
    ...
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -x -q --no-header
```

## Docs

- [AgentDefinition Parameters](docs/agent-definition.md) — full reference for all agent configuration options
