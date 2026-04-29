# codemonkeys

AI agent workflows powered by the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

Agents do one thing. Workflows orchestrate them.

## Why not just use Claude Code?

Claude Code is a general-purpose coding assistant. codemonkeys builds specialized, composable agents with controls that CC doesn't offer:

- **Per-agent permission control.** CC is one permission mode for the whole session. Here, the reviewer runs `dontAsk` with read-only tools (zero prompts), your code presents findings and asks what to fix, then the fixer runs `dontAsk` with write tools. You control exactly where the human decision point is.
- **Right-sized models.** CC uses one model for everything. codemonkeys assigns haiku to mechanical tasks (run ruff, parse output), sonnet to judgment calls (docs review), and opus to deep analysis (security audit, code review). Same quality, fraction of the cost.
- **Deterministic tools run in Python, not via LLM.** The quality workflow runs ruff, mypy, and pytest as subprocess calls — zero tokens, milliseconds, deterministic. The LLM only gets involved when a fix is needed.
- **Structured output.** Agents return Pydantic models, not free text. Findings have typed fields (file, line, severity, category) that downstream code can filter, sort, and act on programmatically.
- **Composable workflows.** Chain agents and CLI tools in Python with explicit control flow: run coverage → write tests → type check → fix → test → review → fix → re-check. CC can't express "run this loop 5 times then move on."
- **Unattended execution.** Run the full pipeline in CI, on a cron, or in a pre-commit hook. No human in the loop until you want one.

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+ and a Claude API key (`ANTHROPIC_API_KEY`).

## Project Structure

```
codemonkeys/
  agents/           # Individual agent definitions (AgentDefinition instances)
  workflows/        # Orchestrate agents and CLI tools into pipelines
  prompts/          # Shared prompt fragments used across agents
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
| `DEFINITION_REVIEWER` | Reviews AgentDefinition files for correctness — description, prompt, permissions, model |

### Workflows

Workflows orchestrate agents and CLI tools into pipelines.

**Review Workflow** — Dispatches all review agents in parallel, collects findings, and optionally dispatches the fixer.

```bash
# Run a full code review
.venv/bin/python -m codemonkeys.workflows.review /path/to/repo

# Review without fix prompt
.venv/bin/python -m codemonkeys.workflows.review . --no-fix

# Review a single file
.venv/bin/python -m codemonkeys.workflows.review . --file src/main.py

# Save results to JSON
.venv/bin/python -m codemonkeys.workflows.review . -o results.json
```

**Quality Workflow** — End-to-end Python quality pipeline: lint, format, coverage, type check, test, code review, security audit, docs review, dependency audit.

```bash
# Run the full pipeline
.venv/bin/python -m codemonkeys.workflows.python_quality

# Skip coverage phase
.venv/bin/python -m codemonkeys.workflows.python_quality --skip-coverage

# Save results to JSON
.venv/bin/python -m codemonkeys.workflows.python_quality -o results.json
```

**Definition Review** — Reviews an AgentDefinition file for correctness and optionally fixes issues.

```bash
.venv/bin/python -m codemonkeys.agents.review_agent_definition codemonkeys/agents/python_code_review.py
```

### Using Agents in Your Own Code

Each agent exports a default constant (built from a factory) and — for review agents — a factory function for customization:

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from codemonkeys.agents import CODE_REVIEWER, TEST_RUNNER, FIXER

# Use the default constant (reviews diff against main)
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

Use factories to customize scope:

```python
from codemonkeys.agents import make_code_reviewer, make_security_auditor

# Review the entire repo instead of just the diff
full_reviewer = make_code_reviewer(scope="repo")

# Review only a specific path
src_auditor = make_security_auditor(scope="repo", path="src/")

# Review changes to a specific file
file_reviewer = make_code_reviewer(scope="diff", path="codemonkeys/agents/python_fixer.py")
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

Create a file in `codemonkeys/agents/` with a factory function and a default constant:

```python
from __future__ import annotations
from typing import Literal
from claude_agent_sdk import AgentDefinition

def make_my_agent(
    scope: Literal["diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    # Build scope-dependent prompt sections
    if scope == "diff":
        method_intro = "Start by running `git diff main...HEAD -- '*.py'` ..."
    else:
        method_intro = "Run `git ls-files '*.py'` ..."

    return AgentDefinition(
        description="Use this agent to ...",  # workflow sees this
        prompt=f"...",                         # agent's full instructions
        model="haiku",                         # model alias
        tools=["Read", "Glob", "Grep", "Bash"],
        disallowedTools=["Bash(git push*)", "Bash(git commit*)"],
        permissionMode="dontAsk",
    )

MY_AGENT = make_my_agent()
```

If the agent doesn't need parameterization (mechanical agents like linters, test runners), use a plain constant instead.

See [docs/agent-definition.md](docs/agent-definition.md) for a full reference of all parameters.

## Writing New Workflows

Create a file in `codemonkeys/workflows/` that uses `ClaudeAgentOptions` with your agents:

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
