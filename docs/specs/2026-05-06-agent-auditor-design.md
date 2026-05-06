# Agent Auditor Design Spec

An agent that analyzes the logs of another agent run to verify it did what it was supposed to — efficiently, without unnecessary tool calls, and without going off-task. Works by comparing the agent's source code (prompt, allowed tools, output schema) against its actual JSONL log output.

## Components

| Component | File | Purpose |
|-----------|------|---------|
| Log Metrics Extractor | `codemonkeys/core/log_metrics.py` | Parse JSONL logs into structured `LogMetrics` |
| Agent Auditor | `codemonkeys/core/agents/agent_auditor.py` | Sonnet agent that judges agent behavior |
| Audit Schema | `codemonkeys/artifacts/schemas/audit.py` | `AgentAudit` and `Issue` Pydantic models |
| CLI Integration | `codemonkeys/run_review.py` | `--audit` flag |

## 1. Log Metrics Extractor

Pure Python — no LLM. Reads a JSONL log file line by line and produces a `LogMetrics` dataclass with deterministic metrics.

**File:** `codemonkeys/core/log_metrics.py`

### Dataclasses

```python
@dataclass
class ToolCall:
    turn: int              # Which assistant turn (1-indexed)
    name: str              # Tool name (Read, Grep, Bash, etc.)
    args_summary: str      # Abbreviated args (file path, pattern, command)

@dataclass
class Turn:
    index: int
    role: str              # "assistant", "user", "system"
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    thinking_content: str  # Raw thinking block text
    tool_calls: list[ToolCall]
    text_content: str      # Non-thinking, non-tool text output

@dataclass
class LogMetrics:
    agent_name: str
    model: str
    allowed_tools: list[str]
    system_prompt: str
    user_prompt: str
    total_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    total_cost: float
    duration_ms: int
    turns: list[Turn]
    tool_calls: list[ToolCall]
    repeated_tool_calls: list[ToolCall]
    unauthorized_tool_calls: list[ToolCall]
    rate_limit_events: list[dict]
    structured_output: str | None
```

### Extraction Logic

1. Read JSONL file line by line
2. First line is `agent_start` — extract `name`, `model`, `tools`, `user_prompt`
3. Each `AssistantMessage` becomes a `Turn`:
   - Parse `content` blocks for `thinking`, `tool_use`, and `text` types
   - Extract token counts from `usage` (including cache breakdown)
   - Build `ToolCall` entries from `tool_use` blocks
4. Last event is `ResultMessage` — extract `cost`, `duration_ms`, `result` (structured output)
5. System prompt comes from the `.md` file in the same log directory
6. Post-processing:
   - Compute `repeated_tool_calls`: group by `(name, args_summary)`, flag any with count > 1
   - Compute `unauthorized_tool_calls`: tool calls where `name` not in `allowed_tools`
   - Collect `RateLimitEvent` entries into `rate_limit_events`

### Serialization

`LogMetrics` serializes to JSON for inclusion in the auditor's user prompt. The `turns` list includes thinking content so the auditor can judge reasoning quality. Tool call args are abbreviated (file paths, not full file contents).

## 2. Agent Auditor

**File:** `codemonkeys/core/agents/agent_auditor.py`
**Factory:** `make_agent_auditor(agent_source_path: str) -> AgentDefinition`
**Model:** sonnet
**Tools:** `Read` (to read the agent source file)

### Input

- `agent_source_path` passed to the factory, embedded in the system prompt so the agent knows which file to read
- Serialized `LogMetrics` JSON as the user prompt

### What It Evaluates

**Instruction compliance** — Did the agent follow its system prompt? Read-only agents that tried to write, reviewers that suggested changes beyond their scope, agents that ignored specific constraints in their prompt.

**Tool discipline (hard violations)** — Tool calls not in the agent's `tools` list. The extractor pre-flags these, but the auditor confirms and provides context.

**Tool discipline (appropriateness)** — Tool calls that were allowed but unrelated to the task. A `changelog_reviewer` reading `setup.py` for no reason. The auditor reads the agent's prompt to understand what files/patterns are relevant, then judges each tool call against that scope.

**Turn efficiency** — Repeated tool calls (same file read twice, same grep pattern). Redundant information gathering (grepping for something already found in a previous read). Wasted turns that produced no useful progress.

**Focus** — Thinking blocks that go off on tangents. Extended reasoning about topics outside the agent's task. The auditor reads the thinking content and judges whether it stayed on-task.

**Output correctness** — Does the structured output match the expected schema from the agent source? Are fields populated with sensible values? Did the agent produce findings that don't match what it was asked to review?

### System Prompt Structure

```
You are an agent auditor. Your job is to analyze whether another agent
performed its task correctly and efficiently.

Read the agent source file at: {agent_source_path}
Extract from it:
- The agent's intended purpose (from the prompt/description)
- The list of approved tools
- The expected output format/schema
- Any specific constraints or guardrails

Then analyze the log metrics provided in the user prompt.
Evaluate: instruction compliance, tool discipline, turn efficiency,
focus, and output correctness.

Return your findings as structured JSON matching the AgentAudit schema.
```

### Output

Returns `AgentAudit` (see schema below).

## 3. Audit Schema

**File:** `codemonkeys/artifacts/schemas/audit.py`

```python
class Issue(BaseModel):
    category: Literal[
        "unauthorized_tool",
        "inappropriate_tool_use",
        "repeated_tool_call",
        "wasted_turn",
        "off_task",
        "instruction_violation",
        "output_problem",
    ]
    turn: int | None
    description: str
    evidence: str

class AgentAudit(BaseModel):
    agent_name: str
    verdict: Literal["pass", "fail"]
    summary: str
    issues: list[Issue]
    token_assessment: str
    recommendations: list[str]
```

**Verdict logic:** "fail" if any issue has category `unauthorized_tool`, `instruction_violation`, `off_task`, or `output_problem`. Efficiency issues (`repeated_tool_call`, `wasted_turn`, `inappropriate_tool_use`) alone produce "pass" with issues noted.

## 4. CLI Integration

**Flag:** `--audit` on `run_review.py` (and `run_agent.py` for single-agent runs)

### Behavior

1. All agents in the run execute normally
2. After all agents complete, the auditor runs once per agent that produced logs
3. For each agent, the auditor:
   - Receives the agent's source `.py` path (the runner knows which factory was called)
   - Receives `LogMetrics` extracted from that agent's JSONL log
4. Audit results display after the normal review output

### Wiring

The runner already tracks:
- Which agent factory produced the `AgentDefinition` (from the `agent_start` event `name` field)
- Where logs are written (`log_dir` + agent name + timestamp)

The `--audit` flag adds `audit=True` to `ReviewConfig`. After the workflow completes, if `audit=True`, the workflow iterates over all log files in the run's `log_dir`, extracts metrics, resolves each agent name back to its source `.py` path via a registry mapping, and dispatches the auditor.

### Agent Source Resolution

A simple mapping from agent name to source path:

```python
AGENT_SOURCES = {
    "python_file_reviewer": "codemonkeys/core/agents/python_file_reviewer.py",
    "architecture_reviewer": "codemonkeys/core/agents/architecture_reviewer.py",
    "changelog_reviewer": "codemonkeys/core/agents/changelog_reviewer.py",
    "readme_reviewer": "codemonkeys/core/agents/readme_reviewer.py",
    "python_code_fixer": "codemonkeys/core/agents/python_code_fixer.py",
    "python_implementer": "codemonkeys/core/agents/python_implementer.py",
    "python_characterization_tester": "codemonkeys/core/agents/python_characterization_tester.py",
    "python_structural_refactorer": "codemonkeys/core/agents/python_structural_refactorer.py",
    "spec_compliance_reviewer": "codemonkeys/core/agents/spec_compliance_reviewer.py",
}
```

This lives in the auditor module. New agents need to be added here.

## Non-Goals

- The auditor does not re-run the agent or modify its output
- The auditor does not have access to the original files the agent reviewed (it judges behavior, not review quality)
- No numeric scoring — verdict is pass/fail with narrative explanation
- The auditor does not audit itself
