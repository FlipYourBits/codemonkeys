# langclaude

LangGraph nodes powered by the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview), with bundled skill markdown files and per-node permissions in the same `Bash(python*)` syntax as Claude Code's `settings.local.json`.

## Install

```bash
uv pip install -e .
# or
pip install -e .
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=...
```

## Quick start

```python
import asyncio
from langgraph.graph import START, END, StateGraph
from langclaude import (
    WorkflowState,
    branch_namer_node,
    feature_implementer_node,
    ShellNode,
    ask_via_stdin,
)

async def main():
    graph = StateGraph(WorkflowState)
    graph.add_node("name", branch_namer_node())
    graph.add_node("checkout", ShellNode(
        name="checkout",
        command=lambda s: ["git", "checkout", "-b", s["branch_name"].strip()],
    ))
    graph.add_node("implement", feature_implementer_node(on_unmatched=ask_via_stdin))
    graph.add_edge(START, "name")
    graph.add_edge("name", "checkout")
    graph.add_edge("checkout", "implement")
    graph.add_edge("implement", END)
    app = graph.compile()

    final = await app.ainvoke({
        "working_dir": "/path/to/repo",
        "task_description": "Add a /healthz endpoint that returns 200 OK",
    })
    print(final)

asyncio.run(main())
```

## Building blocks

### `ClaudeAgentNode`

Wraps `claude_agent_sdk.query()`. Configure system prompt, skills, allowed tools, permission rules, and a prompt template.

```python
from langclaude import ClaudeAgentNode

reviewer = ClaudeAgentNode(
    name="reviewer",
    system_prompt="You review pull requests.",
    skills=["python-clean-code", "python-security"],  # bundled
    allowed_tools=["Read", "Glob", "Grep"],
    allow=["Bash(git diff*)", "Bash(git log*)"],
    deny=["Bash(git push*)"],
    on_unmatched="deny",  # or "allow", or an async callable
    prompt_template="Review the diff for {branch_name}.",
    output_key="review",
)
```

State keys it reads (configurable): `working_dir`, plus whatever the prompt template references.
State key it writes: `output_key` (default `"last_result"`).

### `ShellNode`

Runs a subprocess. Useful for git, build steps, anything non-Claude.

```python
from langclaude import ShellNode

run_tests = ShellNode(name="tests", command="pytest -x")
```

`command` accepts a string (`shlex.split`'d), a list (used as argv), or a callable taking state and returning either form.

### Plain Python functions

LangGraph already accepts any `(state) -> dict` callable as a node — no wrapper needed:

```python
def parse_branch_name(state):
    return {"branch_name": state["branch_name"].strip().splitlines()[0]}

graph.add_node("parse", parse_branch_name)
```

## Permission rules

Rules use the same syntax as Claude Code's `settings.local.json`:

| Rule                     | Meaning                                                      |
|--------------------------|--------------------------------------------------------------|
| `"Read"`                 | every Read call                                              |
| `"Bash(python*)"`        | Bash where `command` matches fnmatch pattern `python*`       |
| `"Bash(git push*)"`      | Bash where `command` matches `git push*`                     |
| `"Edit(*.py)"`           | Edit where `file_path` matches `*.py`                        |
| `"Write(./src/**)"`      | Write where `file_path` matches `./src/**`                   |

Resolution: deny rules win over allow rules. Anything not matched falls through to `on_unmatched`:

- `"deny"` (default) — refuse anything not pre-approved.
- `"allow"` — permit anything not explicitly denied.
- async callable `(tool_name, input_data) -> bool` — your call. We ship `ask_via_stdin` for interactive runs.

## Bundled skills

Reference by stem; the loader resolves them under `langclaude/skills/`:

| Skill                   | Used by default in              |
|-------------------------|---------------------------------|
| `python-clean-code`     | feature_implementer, bug_fixer  |
| `python-security`       | feature_implementer, bug_fixer  |
| `git-guidelines`        | branch_namer                    |

You can add your own via `extra_skills=[...]` (preset nodes) or `skills=[...]` (raw `ClaudeAgentNode`). Pass either a bundled-skill stem or a path to your own `.md` file.

## State

`WorkflowState` is a `TypedDict` with `total=False` — every key is optional, nodes read what they need:

```python
class WorkflowState(TypedDict, total=False):
    working_dir: str
    task_description: str
    branch_name: str
    last_result: str
    artifacts: dict[str, Any]
    error: str | None
```

Use it directly or define your own — anything that's a `dict` at runtime works.

## Run the example

```bash
python -m langclaude.graphs.example /path/to/git/repo "Add a /healthz endpoint"
```

## Tests

```bash
uv pip install -e ".[dev]"
pytest
```
