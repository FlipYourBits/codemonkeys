# Agent Runner Redesign

Minimal agent orchestration framework. Thin wrapper around Claude Agent SDK with imperative async composition.

## Core Principle

No framework. Just a function (`run_agent`) that runs an agent and returns results. Composition is normal Python async code — `asyncio.gather()` for parallel, sequential awaits for pipelines, your logic for routing.

## Data Structures

### AgentDefinition

Frozen dataclass describing an agent. No inheritance, no registry.

```python
@dataclass(frozen=True)
class AgentDefinition:
    name: str
    model: str                              # "opus", "sonnet", "haiku"
    system_prompt: str
    tools: list[str]                        # ["Read", "Grep", "Bash(pytest*)"]
    output_schema: type[BaseModel] | None = None
```

Tools list is a deny-by-default allowlist. Only listed tools are permitted. Bash commands use glob patterns — `"Bash(pytest*)"` allows any command starting with `pytest`.

### RunResult

What `run_agent()` returns.

```python
@dataclass
class RunResult:
    output: BaseModel | None    # Parsed structured output (if schema provided)
    text: str                   # Raw text response
    usage: TokenUsage           # Token accounting
    cost_usd: float             # From SDK's ResultMessage.total_cost_usd
    duration_ms: int
    error: str | None = None    # Non-None if agent failed
```

### TokenUsage

```python
@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
```

## Event System

Single callback signature. No pub/sub framework.

```python
EventHandler = Callable[[Event], None]
```

### Event Types

All events carry `agent_name` and `timestamp`:

- `AgentStarted` — model name
- `ToolCall` — tool_name, tool_input dict
- `ToolResult` — tool_name, output (truncated)
- `ToolDenied` — tool_name, command attempted
- `TokenUpdate` — current usage + cost_usd
- `AgentCompleted` — final RunResult
- `AgentError` — error string

### Usage

```python
# Single handler
result = await run_agent(agent, prompt, on_event=display.handle)

# Fan out to multiple handlers
def fan_out(event):
    display.handle(event)
    logger.handle(event)

result = await run_agent(agent, prompt, on_event=fan_out)
```

## Runner

### `run_agent()`

```python
async def run_agent(
    agent: AgentDefinition,
    prompt: str,
    on_event: EventHandler | None = None,
) -> RunResult:
```

Behavior:
1. Build SDK options from AgentDefinition (model, system prompt, output schema)
2. Construct PreToolUse hook from tools allowlist
3. Call `claude_agent_sdk.query()` with streaming
4. For each streamed message: emit typed events via `on_event`
5. On rate limit: exponential backoff, retry
6. On ResultMessage: extract structured_output, total_cost_usd, build RunResult

### PreToolUse Hook

Built internally from `agent.tools`:
- Parse `"Bash(pattern)"` entries into `{"Bash": ["pattern1", "pattern2"]}`
- For each tool call at runtime:
  - Tool not in allowlist → deny, emit `ToolDenied`
  - Bash command doesn't match any glob pattern → deny, emit `ToolDenied`
  - Otherwise → allow

### Composition

```python
# Parallel
results = await asyncio.gather(
    run_agent(reviewer, f"Review {f}", on_event=display.handle)
    for f in file_batches
)

# Feed downstream
all_findings = [r.output.model_dump() for r in results]
summary = await run_agent(architect, f"Synthesize: {json.dumps(all_findings)}", on_event=display.handle)
```

## Display

### LiveDisplay (Rich)

Default UI subscriber. Renders per-agent cards with live updates.

```python
class LiveDisplay:
    def handle(self, event: Event): ...
    def start(self): ...
    def stop(self): ...
```

Per-agent card shows:
- Agent name + model
- Current tool being called
- Running token count + cost
- Completed agents collapse to summary line
- Denied tools in red, errors highlighted

Footer shows aggregate totals (cost, running agent count).

### FileLogger

One-liner file logging:

```python
class FileLogger:
    def __init__(self, path: str): ...
    def handle(self, event: Event): ...  # Writes JSON line per event
```

## File Layout

```
codemonkeys/
    __init__.py
    agents/                     # Agent factory functions
        __init__.py
        python_file_reviewer.py
        architecture_reviewer.py
        changelog_reviewer.py
        readme_reviewer.py
    core/
        __init__.py
        runner.py               # run_agent() + PreToolUse hook
        events.py               # Event dataclasses + EventHandler type
        types.py                # AgentDefinition, RunResult, TokenUsage
    display/
        __init__.py
        live.py                 # LiveDisplay (Rich)
        logger.py               # FileLogger
    run_review.py               # CLI entry point
```

## What's NOT Here

- No workflow engine / phase system
- No agent registry / type compatibility matching
- No scheduler or DAG runner
- No cost estimation (SDK provides actual cost)
- No debug markdown files
- No EventEmitter class with subscription management
