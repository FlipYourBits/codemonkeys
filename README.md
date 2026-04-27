# langclaude

LangGraph nodes powered by the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview), with bundled skill files and per-node permissions using the same `Bash(python*)` syntax as Claude Code's `settings.local.json`.

## Install

```bash
pip install -e .
```

Set your API key:

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
            ["code_review", "security_audit"],
        ],
        extra_skills=["python-clean-code"],
    )
    final = await pipeline.run()
    print(final)

asyncio.run(main())
```

Steps are strings resolved from the built-in registry. Lists create parallel fan-out. Config overrides and custom nodes are passed as dicts.

## Pipeline

```python
Pipeline(
    working_dir="/path/to/repo",
    task="description of what to do",
    steps=[
        "new_branch",
        "implement_feature",
        "ruff_fix",
        ["code_review", "security_audit", "docs_review"],
        ("ruff_final", "ruff_fix"),       # tuple: (graph_name, registry_key) for aliases
        "custom/commit",
    ],
    extra_skills=["python-clean-code"],   # injected into every node that accepts it
    config={
        "code_review": {"mode": "diff", "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"]},
        "security_audit": {"mode": "diff"},
    },
    custom_nodes={"custom/commit": my_commit_factory},
    verbose=True,
    extra_state={"base_ref": "main"},
)
```

- **steps**: list of registry names, `(alias, registry_key)` tuples, or nested lists for parallel.
- **config**: per-step overrides passed as kwargs to the node factory.
- **custom_nodes**: registered before resolution. Keys must be namespaced (`"custom/name"`).
- **extra_skills**: merged into every node whose factory accepts `extra_skills`.
- **extra_state**: additional key-value pairs merged into the initial state dict.

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

## Built-in nodes

| Factory | Registry name | Default output key | Description |
|---|---|---|---|
| `claude_new_branch_node()` | `new_branch` | `branch_name` | Generates branch name, handles dirty tree, creates branch |
| `claude_feature_implementer_node()` | `implement_feature` | `last_result` | Implements feature from task_description |
| `claude_code_review_node()` | `code_review` | `review_findings` | Runs linters + semantic review. Allow Edit/Write to also fix. |
| `claude_security_audit_node()` | `security_audit` | `security_findings` | Runs security scanners + review. Allow Edit/Write to also fix. |
| `claude_docs_review_node()` | `docs_review` | `docs_findings` | Checks docs for drift. Allow Edit/Write to also fix. |
| `claude_pytest_node()` | `pytest` | `test_findings` | Runs pytest, analyzes failures. Allow Edit/Write to also fix. |
| `claude_coverage_node()` | `coverage` | `coverage_findings` | Runs coverage, finds gaps. Allow Edit/Write to add tests. |
| `claude_dependency_audit_node()` | `dependency_audit` | `dep_findings` | Runs SCA scanners. Allow Edit/Write to upgrade deps. |
| `shell_ruff_fix_node()` | `ruff_fix` | `ruff_fix_output` | Runs `ruff check --fix` |
| `shell_ruff_fmt_node()` | `ruff_fmt` | `ruff_fmt_output` | Runs `ruff format` |

## Permissions control behavior

Each node's behavior is controlled by three levers:

1. **allow/deny** — what tools the agent can use. Default: read-only. Pass Edit/Write to enable fixing.
2. **on_unmatched** — what happens for unmatched tool calls:
   - `"allow"`: auto-approve (CI / fully automatic)
   - `"deny"`: refuse (default)
   - `ask_via_stdin`: prompt the user (interactive)
3. **System prompt** — adjusts automatically based on permissions. Read-only nodes report findings; read-write nodes also fix them.

```python
# Report only (default):
claude_security_audit_node()

# Fix automatically:
claude_security_audit_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
)

# Fix with user approval per edit:
from langclaude import ask_via_stdin
claude_security_audit_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
    on_unmatched=ask_via_stdin,
)
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

`chain()` wires nodes in sequence and adds `START`/`END` automatically. Lists create parallel fan-out.

## Pre-built graphs

**`python_new_feature`** — end-to-end: branch creation, implementation, lint, parallel reviews with fixing enabled, final lint, commit.

```bash
python -m langclaude.graphs.python_new_feature /path/to/repo "Add a /healthz endpoint"
```

**`python_full_repo_review`** — read-only analysis: lint, tests, coverage, code review, security audit, docs review, and dependency audit all run in parallel.

```bash
python -m langclaude.graphs.python_full_repo_review /path/to/repo
```

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

**Plain functions** — any `(state) -> dict` callable is a valid LangGraph node, no wrapper needed.

## Permission rules

Rules use the same syntax as Claude Code's `settings.local.json`:

| Rule | Meaning |
|---|---|
| `"Read"` | every Read call |
| `"Bash(python*)"` | Bash where `command` matches `python*` |
| `"Bash(git push*)"` | Bash where `command` matches `git push*` |
| `"Edit(*.py)"` | Edit where `file_path` matches `*.py` |

Resolution: deny wins over allow. Unmatched tools fall through to `on_unmatched`:

- `"deny"` (default) — refuse anything not pre-approved.
- `"allow"` — permit anything not explicitly denied.
- async callable `(tool_name, input_data) -> bool` — we ship `ask_via_stdin` for interactive runs.

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

Each run writes `last_cost_usd` into state. Other cost levers:

- Use Sonnet for cheap nodes: `model="claude-sonnet-4-6"`.
- Cap turns: `max_turns=10`.
- Tighten `allow` so the agent doesn't roam.

## Output-key collision detection

```python
from langclaude import validate_node_outputs

validate_node_outputs(audit, review, fix)  # raises OutputKeyConflict on collision
```

`last_cost_usd`, `last_result`, and `artifacts` are on a merge-OK allow-list.

## Bundled skills

Node-specific skills (code-review, security-audit, docs-review, git-guidelines) are embedded directly in each node's system prompt. Language-specific skills are separate `.md` files under `langclaude/skills/`, referenced by stem:

| Skill | Used by |
|---|---|
| `python-clean-code` | pass via `extra_skills` |
| `python-security` | pass via `extra_skills` |
| `javascript-clean-code` | pass via `extra_skills` |
| `javascript-security` | pass via `extra_skills` |
| `rust-clean-code` | pass via `extra_skills` |
| `rust-security` | pass via `extra_skills` |

Pass language skills via `extra_skills=["python-clean-code"]` on any node factory, or `skills=[...]` on a raw `ClaudeAgentNode`. Accepts bundled stems or paths to your own `.md` files.

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

Cost reporting (`last_cost_usd`, `max_budget_usd`, `warn_at_pct`) works regardless of backend.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
