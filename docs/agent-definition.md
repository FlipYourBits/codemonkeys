# AgentDefinition Parameters

`AgentDefinition` from `claude_agent_sdk` defines a reusable agent that a coordinator can dispatch. Each agent file in `codemonkeys/agents/` exports one of these.

> **Note on permissions behavior (verified experimentally):**
>
> When an agent runs directly via `ClaudeAgentOptions`, both `tools` and `disallowedTools` are enforced under all permission modes — including `bypassPermissions`.
>
> However, when an agent is dispatched as a subagent by a coordinator, the coordinator's own `bypassPermissions` can override the subagent's `disallowedTools`. The `tools` field (tool visibility) is always enforced regardless.
>
> For subagents, `tools` is the primary gatekeeper — only list the tools the agent should have access to. Use `disallowedTools` for pattern-based restrictions (e.g. `Bash(git push*)`) but be aware these may not be enforced if the coordinator uses `bypassPermissions`.

```python
from claude_agent_sdk import AgentDefinition

MY_AGENT = AgentDefinition(
    description="...",
    prompt="...",
    # ... other params
)
```

## Required

### `description` (str)

Short text explaining what the agent does. The coordinator sees this to decide when and how to dispatch it.

```python
description="Use this agent to run the pytest suite and analyze any test failures."
```

### `prompt` (str)

The full instructions the agent follows. This is the agent's system prompt — it defines scope, method, output format, and exclusions.

```python
prompt="""\
You run the project's test suite and analyze failures.
Report findings only — do not fix issues.
..."""
```

## Tool Control

### `tools` (list[str] | None)

Allowlist of tools the agent can see and use. `None` means all tools are available.

```python
tools=["Read", "Glob", "Grep", "Bash"]
```

### `disallowedTools` (list[str] | None)

Denylist of tools the agent cannot use. Supports fnmatch patterns for tool inputs. Deny always wins over allow.

```python
disallowedTools=["Edit", "Write", "Bash(git push*)", "Bash(git commit*)"]
```

`tools` and `disallowedTools` control which tools the agent can see. `permissionMode` controls whether tool calls need user approval. They are independent — `bypassPermissions` does not override `disallowedTools`.

## Model

### `model` (str | None)

Which Claude model to use. Can be an alias (`"sonnet"`, `"opus"`, `"haiku"`) or a full model ID. `None` inherits from the coordinator.

```python
model="claude-haiku-4-5-20251001"
```

## Execution Control

### `maxTurns` (int | None)

Maximum number of tool-use turns before the agent is forced to stop. A **turn** is one tool-use round trip:

1. Claude responds with one or more tool calls
2. The SDK executes those tools (parallel calls in one response = one turn)
3. Results are fed back to Claude

A final text-only response (no tool calls) does **not** count as a turn.

Example with `maxTurns=3`:

| Turn | What happens |
|------|-------------|
| 1 | Agent runs `git diff` (1 tool call) |
| 2 | Agent reads 8 files in parallel (8 tool calls, still 1 turn) |
| 3 | Agent reads 3 more files (3 tool calls, 1 turn) |
| — | Agent produces findings (text only, not a turn) |

`None` means no limit. Set this as a safety rail against runaway loops.

Suggested values:
- Read-only review agents: `15`
- Fixer agents (read + edit + test): `25`
- Mechanical agents (run one command, parse output): `10`

### `effort` (str | None)

Controls how much reasoning the model does before responding.

| Value | Use case |
|-------|----------|
| `"low"` | Minimal thinking, fastest and cheapest. Mechanical tasks — run a command, parse output. Linter, test runner. |
| `"medium"` | Balanced. Good for agentic tasks that need speed/cost/quality tradeoff. |
| `"high"` | Deep reasoning (the default when unset). Complex coding, code review, security audit. |
| `"max"` | No constraints on token spending. Only for frontier problems where missing something is very costly and token spend doesn't matter. Can cause overthinking on simpler tasks. |
| `"xhigh"` | Opus 4.7 only. Extended capability for long-running tasks (30+ minutes). |

`None` is equivalent to `"high"`. On most workloads `"max"` adds significant cost for relatively small quality gains.

### `background` (bool | None)

Controls whether the coordinator blocks while this agent runs.

- `None` or `False` (default) — **Foreground.** The coordinator waits for this agent to finish before doing anything else. The coordinator gets the agent's result directly.
- `True` — **Background.** The coordinator dispatches this agent and immediately continues with other work. The agent runs concurrently.

**How results come back from background agents:**

Background agents communicate via task messages streamed to the coordinator:

- `TaskStartedMessage` — agent has started
- `TaskProgressMessage` — periodic progress updates (tokens used, tool calls made)
- `TaskNotificationMessage` — agent finished (status: `"completed"`, `"failed"`, or `"stopped"`)

The coordinator can respond to these notifications as they arrive while continuing its own work.

**When to use background agents:**

- Long-running tasks that shouldn't block the coordinator (e.g., running a full test suite while other agents review code)
- Fire-and-forget operations where the coordinator doesn't need the result to proceed
- Improving perceived speed by letting the coordinator respond while background work continues

**Limitations:**

- Background agents run in isolated context — they don't see the coordinator's conversation history. Include any necessary context in the dispatch prompt.
- Subagents (background or not) cannot spawn their own subagents.
- Results come back as task notification messages, not as direct return values like foreground agents.

**Example:**

```python
# A foreground agent — coordinator waits for results
CODE_REVIEWER = AgentDefinition(
    description="Reviews code for issues",
    prompt="...",
    # background not set = foreground (default)
)

# A background agent — coordinator continues immediately
LOG_ANALYZER = AgentDefinition(
    description="Analyzes logs in the background",
    prompt="...",
    background=True,
)
```

## Context

### `skills` (list[str] | None)

Names of Claude Code skill files (`.claude/skills/*.md`) to inject into the agent's context. Not the same as the `codemonkeys/skills/` Python module — those are string constants you embed directly in the `prompt` field.

```python
skills=["python-best-practices"]
```

Most agents don't need this. Embedding prompt text directly via the `prompt` field (or f-string constants from `codemonkeys/skills/`) is simpler and more explicit.

### `memory` (str | None)

Gives the agent access to Claude Code's persistent memory files.

| Value | Scope | Location |
|-------|-------|----------|
| `"user"` | User-level preferences across all projects | `~/.claude/` |
| `"project"` | Project-specific context, committed to git | `.claude/` |
| `"local"` | Machine-specific, gitignored | `.claude.local/` |

`None` means no memory access. Most agents are stateless workers and don't need memory.

### `mcpServers` (list | None)

MCP (Model Context Protocol) servers the agent can connect to, by name or config dict.

```python
mcpServers=["my-database-server"]
```

### `initialPrompt` (str | None)

A user message prepended before the coordinator's dispatch message. Acts as a "pre-prompt" that every invocation of this agent receives automatically.

```python
initialPrompt="Always focus on the src/ directory and ignore vendored code."
```

Rarely needed — if your agent prompt is already purpose-built, there's no gap to fill.

## Permissions

### `permissionMode` (str | None)

Controls whether tool calls need user approval.

| Value | Behavior |
|-------|----------|
| `"default"` | Prompts the user for each tool call |
| `"acceptEdits"` | Auto-approves file edits, asks for other risky operations |
| `"plan"` | Read-only mode, denies all writes |
| `"bypassPermissions"` | Auto-approves everything without asking |
| `"dontAsk"` | Denies anything that would normally prompt (no user interaction) |
| `"auto"` | Auto-approves safe/read-only tools, asks for risky ones |

**Important:** `permissionMode` is independent of `tools`/`disallowedTools`. Setting `bypassPermissions` does not let the agent use tools excluded by `disallowedTools`. The two systems work together:

1. `tools` / `disallowedTools` — can this agent see this tool?
2. `permissionMode` — if yes, does it need user approval?

For unattended agents, use `bypassPermissions` with a tight `disallowedTools` list to control what the agent can actually do.
