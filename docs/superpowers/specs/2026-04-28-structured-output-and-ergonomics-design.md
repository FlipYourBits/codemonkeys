# Structured Output & Pipeline Ergonomics

## Problem

Two friction points in agentpipe's current API:

1. **Every node hand-writes JSON schema instructions** in its system prompt (~30 lines of boilerplate per node, including severity guides). No validation that Claude actually follows the schema.
2. **Downstream nodes regex-parse JSON out of markdown strings** to consume upstream output. `ResolveFindings` uses `re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")` to find findings — fragile and untyped.

## Design

### 1. Dataclass-based structured output

Each node defines an output dataclass in its own file and passes it to the base class via `output=`. The base class (`ClaudeAgentNode` / `ShellNode`) handles two things automatically:

1. **Prompt generation** — appends a `## Output` section to the system prompt with JSON schema, examples, and severity descriptions, all derived from the dataclass's `field(metadata=...)`.
2. **Response parsing** — after the agent responds (or the shell command runs), parses the output into a typed dataclass instance and stores it in state.

There are no shared types. Each node owns its dataclass. Nodes are fully independent.

#### Example output dataclass

```python
from dataclasses import dataclass, field

@dataclass
class ReviewOutput:
    findings: list[dict] = field(
        default_factory=list,
        metadata={"example": [{
            "file": "path/to/file.py",
            "line": 42,
            "severity": "HIGH",
            "category": "logic_error",
            "source": "python_code_review",
            "description": "Off-by-one in loop bound.",
            "recommendation": "Use < instead of <=.",
            "confidence": "high",
        }]},
    )
    summary: dict[str, int] = field(
        default_factory=dict,
        metadata={"example": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}},
    )
```

Fields that need constrained values use `enum` and `descriptions` in metadata:

```python
@dataclass
class ReviewOutput:
    findings: list[dict] = field(
        default_factory=list,
        metadata={"example": [{
            "file": "path/to/file.py",
            "line": 42,
            "severity": "HIGH",
            "category": "logic_error",
            "source": "python_code_review",
            "description": "Off-by-one in loop bound.",
            "recommendation": "Use < instead of <=.",
            "confidence": "high",
        }]},
    )
    summary: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "example": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0},
        },
    )
```

And each node customizes field semantics through metadata on the example dict's nested fields. For the severity guide specifically, nodes pass a `severity_guide` key in the findings field metadata:

```python
findings: list[dict] = field(
    default_factory=list,
    metadata={
        "example": [{ ... }],
        "severity_guide": {
            "HIGH": "Bug that will cause incorrect behavior in production",
            "MEDIUM": "Latent bug under specific conditions",
            "LOW": "Minor concern worth surfacing but not blocking",
        },
    },
)
```

A security audit node uses different descriptions:

```python
findings: list[dict] = field(
    default_factory=list,
    metadata={
        "example": [{ ... }],
        "severity_guide": {
            "HIGH": "Directly exploitable — RCE, auth bypass, data breach",
            "MEDIUM": "Exploitable under specific but realistic conditions",
            "LOW": "Defense-in-depth or limited-impact issue",
        },
    },
)
```

The `severity_guide` is prompt-generation config only — `dataclasses.asdict()` ignores all metadata, so it never appears in output.

#### Schema generation (`agentpipe/schema.py`)

A function `generate_output_instructions(cls) -> str` that:

1. Walks `dataclasses.fields(cls)`
2. Builds a JSON example from `metadata["example"]` values
3. If a field has `metadata["severity_guide"]`, appends a severity section:
   ```
   Severity:
   - HIGH: Bug that will cause incorrect behavior in production
   - MEDIUM: Latent bug under specific conditions
   - LOW: Minor concern worth surfacing but not blocking
   ```
4. Returns a complete markdown block appended to the system prompt

This replaces both the hand-written `## Output` section and the severity guide in each node's `_SKILL`. The `_SKILL` is reduced to: behavior instructions, triage rules, exclusions.

#### Response parsing (`agentpipe/schema.py`)

A function `parse_output(cls, text: str) -> instance | None` that:

1. Extracts JSON from the response (fenced block or raw JSON)
2. Converts the dict to the dataclass via `cls(**data)`
3. Returns `None` on failure (malformed JSON, missing required fields)

No external dependencies — stdlib `dataclasses` + `json`. ~30-40 lines.

#### Integration with `ClaudeAgentNode`

New optional `output` parameter on `ClaudeAgentNode.__init__`:

```python
class ClaudeAgentNode:
    def __init__(self, *, output: type | None = None, ...):
        self.output_cls = output
        if output is not None:
            self.system_prompt += "\n\n" + generate_output_instructions(output)
```

In `__call__`, after getting the response:

```python
final = result_text if result_text else "\n".join(text_chunks).strip()
if self.output_cls is not None:
    parsed = parse_output(self.output_cls, final)
    if parsed is not None:
        final = parsed
# Stores either a typed dataclass instance or raw text as fallback
return {self.name: final, "last_cost_usd": tracker.last_cost_usd}
```

#### Integration with `ShellNode`

Same optional `output` parameter. If set, parse stdout as JSON into the dataclass after the command runs:

```python
stdout = result.stdout.strip()
if self.output_cls is not None:
    parsed = parse_output(self.output_cls, stdout)
    if parsed is not None:
        return {self.name: parsed}
return {self.name: stdout}
```

Most ShellNodes won't use this — `PythonLint`, `PythonFormat`, and `PythonEnsureTools` produce plain text that nothing downstream consumes structurally. `PythonTypeCheck` is the exception: its embedded script transforms mypy JSON into a findings-like format. Adding `output=TypeCheckOutput` parses that stdout into a typed object.

#### Integration with `ResolveFindings`

ResolveFindings doesn't know any node's output schema. It serializes whatever typed objects are in state into the prompt for its inner Claude agent:

```python
for key in self._reads_from_keys:
    upstream = state[key]
    if dataclasses.is_dataclass(upstream):
        serialized = json.dumps(dataclasses.asdict(upstream), indent=2)
        parts.append(f"### {key}\n```json\n{serialized}\n```")
    elif isinstance(upstream, str):
        parts.append(f"### {key}\n{upstream}")
```

Claude reads the JSON and interprets it — no shared contracts, no coupling. The inner agent handles whatever structure each upstream node produced.

The existing regex-based `_extract_findings` becomes the fallback for string-typed upstream output (nodes without `output=`).

### 2. Better imports from `agentpipe.nodes`

Export all current node classes from `agentpipe/nodes/__init__.py`:

```python
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_lint import PythonLint
# ... etc
```

One-line import for building a pipeline:

```python
from agentpipe.nodes import PythonLint, PythonTest, PythonCodeReview, ResolveFindings
```

## Migration path for existing nodes

Each node currently has a hand-written `## Output` section and severity guide in its `_SKILL` string. Migration per node:

1. Define an output dataclass in the node's file with `metadata["example"]` and `metadata["severity_guide"]`
2. Remove `## Output` and severity guide sections from `_SKILL`
3. Pass `output=ReviewOutput` to `super().__init__()`
4. The auto-generated schema + severity guide replaces the hand-written sections

Each node's dataclass is independent — no shared types, no imports between nodes.

## Files to create/modify

| File | Change |
|---|---|
| `agentpipe/schema.py` | **New.** `generate_output_instructions()`, `parse_output()` |
| `agentpipe/nodes/base.py` | Add `output` param to `ClaudeAgentNode` and `ShellNode` |
| `agentpipe/nodes/python_code_review.py` | Define `ReviewOutput`, remove `## Output` + severity from `_SKILL`, pass `output=` |
| `agentpipe/nodes/python_security_audit.py` | Same pattern |
| `agentpipe/nodes/docs_review.py` | Same pattern |
| `agentpipe/nodes/python_test.py` | Define `TestOutput`, same pattern |
| `agentpipe/nodes/python_dependency_audit.py` | Define `AuditOutput`, same pattern |
| `agentpipe/nodes/python_type_check.py` | Define `TypeCheckOutput`, pass `output=` |
| `agentpipe/nodes/resolve_findings.py` | Serialize typed state via `dataclasses.asdict()`, keep regex fallback |
| `agentpipe/__init__.py` | Clean up exports |
| `agentpipe/nodes/__init__.py` | Export all current node classes |

## What this does NOT change

- Node class hierarchy (`ClaudeAgentNode`, `ShellNode`)
- Pipeline topology (`steps`, sequential + parallel via nested lists)
- Permission system (`allow`/`deny`/`on_unmatched`)
- Budget tracking
- Display / verbosity system
- Hand-written `_SKILL` content (behavior, method, triage, exclusions)
- The `_old/` compatibility layer

## Testing

- Unit tests for `generate_output_instructions()` — verify correct JSON examples and severity guide from dataclass metadata
- Unit tests for `parse_output()` — valid JSON, malformed JSON, missing fields, fenced vs raw JSON
- Unit test: node with `output=` stores a dataclass instance in state
- Unit test: node without `output=` stores raw text (backward compat)
- Unit test: `ResolveFindings` serializes dataclass upstream and falls back to string upstream
- Regression: all existing tests pass unchanged
