# agentpipe

Deterministic AI pipelines with per-node model selection, least-privilege permissions, and guaranteed execution. Built on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview).

## Why not just use Claude Code?

Claude Code (with plugins like superpowers) is excellent for interactive work — brainstorming, implementing features with human-in-the-loop review, debugging. A skilled developer steering Claude through a conversation will outperform any automated pipeline for novel, judgment-heavy tasks.

agentpipe solves a different problem: **repeatable, unattended, cost-controlled code operations** where you need guarantees that a conversation can't provide.

### What agentpipe gives you

**Per-node model selection.** Each pipeline step runs its own Claude instance on a specific model. Run dependency audit on Haiku ($0.25/MTok), test analysis on Sonnet ($3/MTok), and code review on Opus ($15/MTok). A Claude Code session uses one model for all subagents unless you manually override each dispatch.

**Per-node permissions.** Each node gets explicit allow/deny lists. The code reviewer can Read and Grep but can't Edit. The test runner can run pytest but can't pip install. The commit node can `git add` and `git commit` but not `git push`. Claude Code subagents inherit the session's permission mode — a subagent asked to "review code" could still edit files if it decides to.

**Guaranteed execution.** The pipeline topology is deterministic. If you define 5 parallel review nodes, all 5 run. A skill prompt says "run lint, then review, then test" but Claude might skip steps, combine them, or decide one isn't needed. The pipeline doesn't interpret — it executes.

**Cost tracking and controls.** Every node reports its token cost. Per-node budget caps, model tier selection, and structured run logs (`.agentpipe/runs/`) give you visibility and control over spend. A Claude Code session gives you a single bill at the end.

**Structured, machine-readable output.** Each node produces JSON findings with severity, file, line, category. Downstream nodes consume this programmatically — `resolve_findings` parses upstream JSON and presents a numbered list for the user to triage. Claude Code subagents produce free-text summaries that require human interpretation.

### When Claude Code alone is enough

- **Interactive development** — brainstorming, planning, implementing features with a human reviewing each step.
- **One-off tasks** — "fix this bug," "add this endpoint," "refactor this module." The overhead of defining a pipeline isn't worth it for work you'll do once.
- **Novel, ambiguous work** — tasks where you don't know the steps upfront. A conversation adapts; a pipeline executes a fixed topology.
- **Small repos or solo projects** — if the cost of running 5 parallel review nodes isn't justified by the codebase size or team requirements.

### When you need agentpipe

- **CI/CD quality gates** — run on every PR with guaranteed lint, test, review, security scan, dependency audit. Post structured results. No human babysitting.
- **Compliance/audit pipelines** — nightly security scan with Opus, license check with Haiku, SBOM generation with a shell node. Read-only permissions guarantee audit integrity.
- **Codebase migrations** — plan → implement → test → review across 50 modules. Each step has least-privilege permissions and a cost ceiling. Track spend per module.
- **Multi-team repos** — Python quality gate for backend, JS gate for frontend, shared security audit. Each sub-pipeline uses language-specific skills and models.

## Install

```bash
pip install -e .              # core only
pip install -e ".[python]"    # + pytest, pytest-cov, pip-audit, ruff
pip install -e ".[dev]"       # + pytest-asyncio
```

```bash
export ANTHROPIC_API_KEY=...
```

## Quick start

```python
import asyncio
from agentpipe import Pipeline

async def main():
    pipeline = Pipeline(
        working_dir="/path/to/repo",
        task="Add a /healthz endpoint that returns 200 OK",
        steps=[
            "git_new_branch",
            "implement_feature",
            "python_lint",
            "python_format",
            ["code_review", "security_audit", "python_test"],
        ],
    )
    result = await pipeline.run()
    pipeline.print_results()

asyncio.run(main())
```

Steps are strings resolved from the built-in registry. Lists create parallel fan-out via `asyncio.gather`.

## Built-in nodes

Every node does one thing. The registry name doubles as the output key in state.

### Workflow

| Node | What it does |
|---|---|
| `git_new_branch` | Generates a branch name from the task description. Interactive mode prompts for approval and handles dirty-tree safety. |
| `git_commit` | Reviews uncommitted changes, writes a conventional commit message, stages and commits. |
| `implement_feature` | Implements a feature described in `task_description`. Reads the repo, proposes the smallest change, makes edits. |
| `python_plan_feature` | Interactive planning: explores the codebase and produces a step-by-step implementation plan. |
| `python_implement_feature` | Python-specific implementation with interactive review. Follows clean-code and security guidelines. |

### Quality

Each owns a single concern. They do not overlap — code review doesn't run linters, security audit doesn't check code quality, etc.

| Node | What it does |
|---|---|
| `code_review` | Semantic code review. Logic errors, deep nesting, error handling gaps, resource leaks, concurrency bugs, dead code. Does NOT run linters or tests. |
| `security_audit` | Traces data flow from inputs to sinks. Injection, auth bypass, hardcoded secrets, unsafe deserialization, data exposure. No external scanners. |
| `docs_review` | Doc drift detection. Checks docstrings, README, CHANGELOG against actual code for accuracy. |
| `python_test` | Runs pytest, reads failing tests and the code under test to identify root causes. |
| `python_coverage` | Runs `pytest --cov`, identifies uncovered lines and branches. Supports `mode="diff"` or `mode="full"`. |
| `dependency_audit` | Runs whichever SCA tools are installed (pip-audit, npm audit, govulncheck, cargo audit, bundler-audit). |

### Python tooling

| Node | What it does |
|---|---|
| `python_lint` | Runs `ruff check --fix`. Pass `fix=False` for check-only. |
| `python_format` | Runs `ruff format`. |

All quality nodes default to read-only. Pass Edit/Write in the allow list to enable fixing.

## Permissions

Every node always tries to find and fix issues. Permissions decide what actually happens:

1. **allow/deny** — what tools the agent can use. Default: read-only (Edit/Write denied).
2. **on_unmatched** — what happens for tool calls not covered by allow/deny:
   - `"deny"`: block (default — report-only)
   - `"allow"`: auto-approve (CI / fully automatic)
   - `ask_via_stdin`: prompt the user per call

```python
# Report only (default):
code_review_node()

# Auto-fix everything:
code_review_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
)

# Prompt user per edit:
from agentpipe import ask_via_stdin
code_review_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
    on_unmatched=ask_via_stdin,
)
```

### Permission rule syntax

Same syntax as Claude Code's `settings.local.json`:

| Rule | Meaning |
|---|---|
| `"Read"` | every Read call |
| `"Bash(python*)"` | Bash where `command` matches `python*` |
| `"Bash(git push*)"` | Bash where `command` matches `git push*` |
| `"Edit(*.py)"` | Edit where `file_path` matches `*.py` |

Deny always wins over allow.

## Pipeline

`Pipeline` resolves step names from the registry, injects config, and runs the workflow with `asyncio`.

```python
from agentpipe import Pipeline
from agentpipe.nodes.base import Verbosity

Pipeline(
    working_dir="/path/to/repo",
    task="description of what to do",
    steps=[
        "git_new_branch",
        "implement_feature",
        "python_lint",
        ["code_review", "security_audit", "python_test"],  # parallel
        ("lint_final", "python_lint"),  # tuple: (alias, registry_key)
        "custom/commit",
    ],
    config={
        "code_review": {"mode": "diff"},
        "python_test": {"requires": ["code_review"]},
    },
    custom_nodes={"custom/commit": my_commit_factory},
    model="claude-sonnet-4-6",
    verbosity=Verbosity.normal,
    extra_state={"base_ref": "main"},
)
```

| Parameter | What it does |
|---|---|
| **steps** | Registry names, `(alias, registry_key)` tuples for duplicates, or nested lists for parallel fan-out. |
| **config** | Per-step overrides passed as kwargs to the node factory. Supports `requires` to inject prior node output. |
| **custom_nodes** | Registered before resolution. Keys should be namespaced (`"custom/name"`). |
| **model** | Default model for all nodes. Per-node config overrides. |
| **verbosity** | `Verbosity.silent` (default), `.normal`, or `.verbose`. Per-node config overrides. |
| **extra_state** | Additional key-value pairs merged into the initial state dict. |

## Registry

Every built-in node has a string name. User nodes are registered under a namespace:

```python
from agentpipe import register, resolve, list_builtins

list_builtins()
# ['code_review', 'dependency_audit', 'docs_review',
#  'git_commit', 'git_new_branch', 'implement_feature',
#  'python_coverage', 'python_format', 'python_implement_feature',
#  'python_lint', 'python_plan_feature', 'python_test',
#  'security_audit']

register("deploy", my_deploy_factory, namespace="acme")
resolve("acme/deploy")  # returns my_deploy_factory
```

## Pre-built pipelines

**`python_new_feature`** — end-to-end: branch → plan → implement → lint → format → test → coverage → code review → security audit → docs review → dependency audit → final lint → commit.

```bash
python -m agentpipe.graphs.python_new_feature /path/to/repo "Add a /healthz endpoint"
```

**`python_quality_gate`** — lint → format → parallel (test + code review + security audit + docs review + dependency audit) → resolve findings → final lint. No branch, no commit.

```bash
python -m agentpipe.graphs.python_quality_gate /path/to/repo
```

## Building blocks

**`ClaudeAgentNode`** — wraps `claude_agent_sdk.query()`:

```python
from agentpipe import ClaudeAgentNode, PYTHON_CLEAN_CODE

reviewer = ClaudeAgentNode(
    name="reviewer",
    system_prompt="You review pull requests.",
    skills=[PYTHON_CLEAN_CODE],
    allow=["Read", "Glob", "Grep", "Bash(git diff*)"],
    deny=["Bash(git push*)"],
    prompt_template="Review the diff for {git_new_branch}.",
)
```

**`ShellNode`** — runs a subprocess:

```python
from agentpipe import ShellNode

run_tests = ShellNode(name="tests", command="pytest -x")
```

**Plain functions** — any `(state) -> dict` callable works as a node.

## Cost controls

```python
ClaudeAgentNode(
    ...,
    max_budget_usd=0.50,
    hard_cap=False,            # False = warning-only
    warn_at_pct=[0.8, 0.95],
)
```

Each run writes `last_cost_usd` into state and logs per-node costs to `.agentpipe/runs/`. Other levers: cheaper models, turn caps (`max_turns=10`), tighter allow lists.

## Language skills

Language-specific clean code and security guidance are constants under `agentpipe.skills`:

```python
from agentpipe.skills import PYTHON_CLEAN_CODE, PYTHON_SECURITY

implement_feature_node(extra_skills=[PYTHON_CLEAN_CODE])
```

| Constant | Language |
|---|---|
| `PYTHON_CLEAN_CODE`, `PYTHON_SECURITY` | Python |
| `JAVASCRIPT_CLEAN_CODE`, `JAVASCRIPT_SECURITY` | JavaScript |
| `RUST_CLEAN_CODE`, `RUST_SECURITY` | Rust |

Pass via `extra_skills` on any node factory, or `skills` on a raw `ClaudeAgentNode`.

## Bedrock and Vertex AI

The Claude Agent SDK honors the same backend toggles as Claude Code:

```bash
# Bedrock
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-west-2

# Vertex AI
export CLAUDE_CODE_USE_VERTEX=1
export CLOUD_ML_REGION=us-east5
export ANTHROPIC_VERTEX_PROJECT_ID=my-project
```

Pass the provider-specific model ID directly:

```python
implement_feature_node(model="us.anthropic.claude-opus-4-7-20251201-v1:0")
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```
