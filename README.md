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
from langgraph.graph import StateGraph
from langclaude import chain, claude_new_branch_node, claude_feature_implementer_node

async def main():
    graph = StateGraph(dict)
    chain(graph,
        ("new_branch", claude_new_branch_node()),
        ("implement", claude_feature_implementer_node()),
    )
    app = graph.compile()

    final = await app.ainvoke({
        "working_dir": "/path/to/repo",
        "task_description": "Add a /healthz endpoint that returns 200 OK",
    })
    print(final)

asyncio.run(main())
```

`chain()` wires nodes in sequence and adds `START`/`END` automatically. Lists create parallel processes:

```python
chain(graph,
    ("implement", claude_feature_implementer_node(extra_skills=["python-clean-code"])),
    ("ruff_fix", shell_ruff_fix_node()),
    [
        ("code_review", claude_code_review_node(mode="diff")),
        ("security_audit", claude_security_audit_node(mode="diff")),
    ],
    ("issue_fixer", claude_issue_fixer_node()),
)
```

## Built-in nodes

Node factory functions are prefixed by type: `claude_` (Claude Agent SDK), `shell_` (subprocess), `py_` (pure Python).

### Claude nodes

| Factory | Default output key | Description |
|---|---|---|
| `claude_new_branch_node()` | `branch_name` | Generates a branch name, prompts for approval (interactive mode), checks for dirty tree (stash/commit/carry), and creates + switches to the branch. Pass `mode="auto"` for CI. |
| `claude_feature_implementer_node()` | `last_result` | Implements a feature described in `task_description`. Reads code and makes edits. Pass `extra_skills=["python-clean-code"]` for language-specific guidance. |
| `claude_bug_fixer_node()` | `last_result` | Diagnoses and fixes a bug from `task_description`. Adds a regression test. |
| `claude_code_review_node()` | `review_findings` | Runs linters, git diff, and type-checkers via Bash, then performs semantic code review. Supports `mode="diff"` (scoped to changes) or `mode="full"` (whole repo). |
| `claude_security_audit_node()` | `security_findings` | Runs security scanners (semgrep, gitleaks, pip-audit, etc.) via Bash, then performs semantic security review. Supports `mode="diff"` or `mode="full"`. |
| `claude_docs_review_node()` | `docs_findings` | Reads doc files and checks for drift against the code. Supports `mode="diff"` or `mode="full"`. |
| `claude_issue_fixer_node()` | `applied_fixes` | Consumes findings from review nodes and applies fixes. Supports `mode="interactive"` (prompt per finding), `mode="auto"` (severity threshold), or `mode="all"`. |

### Shell nodes

| Factory | Default output key | Description |
|---|---|---|
| `shell_ruff_fix_node()` | `ruff_fix_output` | Runs `ruff check --fix` to auto-fix lint violations. Pass `fix=False` for check-only. |
| `shell_ruff_fmt_node()` | `ruff_fmt_output` | Runs `ruff format` to reformat code. |

Both invoke `python -m ruff` so they work whether or not the venv is activated. Ruff is a runtime dependency.

### Python nodes

| Factory | Default output key | Description |
|---|---|---|
| `py_pytest_runner_node()` | `test_findings` | Runs pytest with `pytest-json-report`, parses failures into structured findings. Also writes `test_summary`. |
| `py_pytest_coverage_node()` | `coverage_findings` | Runs `pytest --cov`, parses coverage JSON, emits uncovered line ranges as findings. Supports `mode="diff"` (only changed files) or `mode="full"`. Also writes `coverage_summary`. |
| `py_dependency_audit_node()` | `dep_findings` | Runs whichever SCA tools are installed (pip-audit, npm audit, govulncheck, cargo audit, bundler-audit) and parses results into findings. |

### Low-level building blocks

**`ClaudeAgentNode`** — wraps `claude_agent_sdk.query()`. All `claude_*` factories build on this. Use it directly for custom nodes:

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

## Pre-built graphs

**`python_new_feature`** — end-to-end: branch creation, implementation, lint, test, parallel reviews, issue fixing, bug fixing, final lint, commit.

```bash
python -m langclaude.graphs.python_new_feature /path/to/repo "Add a /healthz endpoint"
```

**`python_full_repo_review`** — read-only analysis: lint, tests, coverage, code review, security audit, docs review, and dependency audit all run in parallel.

```bash
python -m langclaude.graphs.python_full_repo_review /path/to/repo
```

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

Reference by stem; the loader resolves them under `langclaude/skills/`:

| Skill | Used by |
|---|---|
| `code-review` | `claude_code_review_node` |
| `docs-review` | `claude_docs_review_node` |
| `security-audit` | `claude_security_audit_node` |
| `git-guidelines` | `claude_new_branch_node` |
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
