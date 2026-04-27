# langclaude

LangGraph nodes powered by the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview). Each node is a self-contained Claude agent session that owns a single concern — run a tool, analyze, and optionally fix — controlled by permissions.

## Install

```bash
pip install -e .
```

```bash
export ANTHROPIC_API_KEY=...
```

## Quick start

```python
import asyncio
from langclaude import Pipeline

async def main():
    pipeline = Pipeline(
        working_dir="/path/to/repo",
        task="Add a /healthz endpoint that returns 200 OK",
        steps=[
            "new_branch",
            "implement_feature",
            "ruff_fix",
            "ruff_fmt",
            ["code_review", "security_audit", "pytest"],
        ],
        extra_skills=["python-clean-code"],
    )
    final = await pipeline.run()
    print(final)

asyncio.run(main())
```

Steps are strings resolved from the built-in registry. Lists create parallel fan-out.

## Built-in nodes

Every node does one thing. The table is grouped by what that thing is.

### Workflow nodes

| Factory | Registry name | Output key | What it does |
|---|---|---|---|
| `claude_new_branch_node()` | `new_branch` | `branch_name` | Generates a branch name from the task description. In interactive mode, prompts for approval and handles dirty-tree safety (stash/commit/carry). Falls back to auto mode when stdin isn't a TTY. |
| `claude_feature_implementer_node()` | `implement_feature` | `last_result` | Implements a feature described in `task_description`. Reads the repo, proposes the smallest change, makes edits. Does not run tests. |

### Quality nodes

Each owns a single concern. They do not overlap — code review doesn't run linters, security audit doesn't check code quality, etc.

| Factory | Registry name | Output key | What it does |
|---|---|---|---|
| `claude_code_review_node()` | `code_review` | `review_findings` | **Semantic code review.** Reads the code and looks for things linters can't catch: logic errors, functions >50 lines, deep nesting, error handling gaps, resource leaks, concurrency bugs, API contract violations, dead code. Does NOT run linters, type-checkers, tests, or security scanners. |
| `claude_security_audit_node()` | `security_audit` | `security_findings` | **Security review.** Runs installed security scanners (semgrep, gitleaks, etc.) then traces data flow through the code looking for injection, auth bypass, hardcoded secrets, unsafe deserialization, data exposure. Does NOT check code quality or run tests. |
| `claude_docs_review_node()` | `docs_review` | `docs_findings` | **Doc drift detection.** Checks docstrings, README, and CHANGELOG against the actual code for accuracy. Catches stale examples, missing docs for new public APIs, inconsistent terminology. Does NOT review code quality or security. |
| `claude_pytest_node()` | `pytest` | `test_findings` | **Test runner.** Runs pytest, reads failing tests and the code under test to identify root causes. |
| `claude_coverage_node()` | `coverage` | `coverage_findings` | **Coverage analysis.** Runs `pytest --cov`, identifies uncovered lines and branches. Supports `mode="diff"` (changed files only) or `mode="full"`. |
| `claude_dependency_audit_node()` | `dependency_audit` | `dep_findings` | **Dependency vulnerabilities.** Runs whichever SCA tools are installed (pip-audit, npm audit, govulncheck, cargo audit, bundler-audit). |

### Deterministic nodes

| Factory | Registry name | Output key | What it does |
|---|---|---|---|
| `shell_ruff_fix_node()` | `ruff_fix` | `ruff_fix_output` | Runs `ruff check --fix`. Pass `fix=False` for check-only. |
| `shell_ruff_fmt_node()` | `ruff_fmt` | `ruff_fmt_output` | Runs `ruff format`. |

All quality nodes default to read-only. Pass Edit/Write in the allow list to enable fixing — see [Permissions control behavior](#permissions-control-behavior).

## Permissions control behavior

Each node's behavior is controlled by three levers:

1. **allow/deny** — what tools the agent can use. Default: read-only. Pass Edit/Write to enable fixing.
2. **on_unmatched** — what happens for tool calls not covered by allow/deny:
   - `"deny"`: block (default — safest)
   - `"allow"`: auto-approve (CI / fully automatic)
   - `ask_via_stdin`: prompt the user interactively
3. **System prompt** — adjusts automatically. Read-only nodes report findings; read-write nodes also fix them.

```python
# Report only (default):
claude_code_review_node()

# Review and fix automatically:
claude_code_review_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
)

# Review and fix with user approval per edit:
from langclaude import ask_via_stdin
claude_code_review_node(
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

`Pipeline` resolves step names from the registry, injects config, and builds a LangGraph workflow.

```python
Pipeline(
    working_dir="/path/to/repo",
    task="description of what to do",
    steps=[
        "new_branch",
        "implement_feature",
        "ruff_fix",
        ["code_review", "security_audit", "pytest"],  # parallel
        ("ruff_final", "ruff_fix"),  # tuple: (graph_name, registry_key)
        "custom/commit",
    ],
    extra_skills=["python-clean-code"],
    config={
        "code_review": {"mode": "diff"},
        "coverage": {"mode": "diff", "base_ref_key": "base_ref"},
    },
    custom_nodes={"custom/commit": my_commit_factory},
    verbose=True,
    extra_state={"base_ref": "main"},
)
```

| Parameter | What it does |
|---|---|
| **steps** | List of registry names, `(alias, registry_key)` tuples for duplicates, or nested lists for parallel fan-out. |
| **config** | Per-step overrides passed as kwargs to the node factory. |
| **custom_nodes** | Registered before resolution. Keys must be namespaced (`"custom/name"`). |
| **extra_skills** | Merged into every node whose factory accepts `extra_skills`. |
| **extra_state** | Additional key-value pairs merged into the initial state dict. |

## Registry

Every built-in node has a string name. User nodes are registered under a namespace:

```python
from langclaude import register, resolve, list_builtins

list_builtins()
# ['code_review', 'coverage', 'dependency_audit', 'docs_review',
#  'implement_feature', 'new_branch', 'pytest', 'ruff_fix', 'ruff_fmt',
#  'security_audit']

register("deploy", my_deploy_factory, namespace="acme")
resolve("acme/deploy")  # returns my_deploy_factory
```

## Pre-built graphs

Both graphs use `Pipeline` under the hood.

**`python_new_feature`** — end-to-end: branch creation, implementation, lint + format, then all quality nodes in parallel (with fixing enabled), final lint, commit.

```bash
python -m langclaude.graphs.python_new_feature /path/to/repo "Add a /healthz endpoint"
```

**`python_full_repo_review`** — read-only: ruff (check-only), tests, coverage, code review, security audit, docs review, dependency audit — all in parallel. No edits, no branch, no commit.

```bash
python -m langclaude.graphs.python_full_repo_review /path/to/repo
```

## Manual wiring with chain()

For full control, skip `Pipeline` and wire nodes directly:

```python
from langgraph.graph import StateGraph
from langclaude import chain, claude_new_branch_node, claude_feature_implementer_node

graph = StateGraph(dict)
chain(graph,
    ("new_branch", claude_new_branch_node()),
    ("implement", claude_feature_implementer_node()),
    [
        ("code_review", claude_code_review_node(mode="diff")),
        ("security_audit", claude_security_audit_node(mode="diff")),
    ],
)
app = graph.compile()
```

`chain()` wires nodes in sequence with `START`/`END` added automatically. Lists create parallel fan-out.

## Low-level building blocks

**`ClaudeAgentNode`** — wraps `claude_agent_sdk.query()`. All `claude_*` factories build on this:

```python
from langclaude import ClaudeAgentNode

reviewer = ClaudeAgentNode(
    name="reviewer",
    system_prompt="You review pull requests.",
    skills=["python-clean-code"],
    allow=["Read", "Glob", "Grep", "Bash(git diff*)"],
    deny=["Bash(git push*)"],
    prompt_template="Review the diff for {branch_name}.",
    output_key="review",
)
```

**`ShellNode`** — runs a subprocess. `command` accepts a string, a list, or a callable taking state:

```python
from langclaude import ShellNode

run_tests = ShellNode(name="tests", command="pytest -x")
```

**Plain functions** — any `(state) -> dict` callable is a valid LangGraph node.

## Cost controls

```python
ClaudeAgentNode(
    ...,
    max_budget_usd=0.50,       # hard cap — SDK aborts the run
    hard_cap=False,            # set False for warning-only (no abort)
    warn_at_pct=[0.8, 0.95],  # warn at 80% and 95%
    on_warn=None,              # default: print to stderr
)
```

Each run writes `last_cost_usd` into state. Other levers: cheaper models (`model="claude-sonnet-4-6"`), turn caps (`max_turns=10`), tighter allow lists.

## Output-key collision detection

```python
from langclaude import validate_node_outputs

validate_node_outputs(audit, review, coverage)  # raises OutputKeyConflict
```

`last_cost_usd`, `last_result`, and `artifacts` are on a merge-OK allow-list.

## Language skills

Node-specific behavior (what code review looks for, what security audit traces, etc.) is embedded directly in each node's system prompt. Language-specific clean code and security guidance are separate `.md` files under `langclaude/skills/`:

| Skill | Usage |
|---|---|
| `python-clean-code` | `extra_skills=["python-clean-code"]` |
| `python-security` | `extra_skills=["python-security"]` |
| `javascript-clean-code` | `extra_skills=["javascript-clean-code"]` |
| `javascript-security` | `extra_skills=["javascript-security"]` |
| `rust-clean-code` | `extra_skills=["rust-clean-code"]` |
| `rust-security` | `extra_skills=["rust-security"]` |

Pass on any node factory via `extra_skills`, or on a raw `ClaudeAgentNode` via `skills`. Accepts bundled stems or paths to your own `.md` files.

## Using Amazon Bedrock or Google Vertex AI

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
claude_feature_implementer_node(model="us.anthropic.claude-opus-4-7-20251201-v1:0")
```

Cost reporting works regardless of backend.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
