# Structured Output & Pipeline Ergonomics

## Problem

Two friction points in agentpipe's current API:

1. **Every node hand-writes JSON schema instructions** in its system prompt (~30 lines of boilerplate per node). No validation that Claude actually follows the schema.
2. **Downstream nodes regex-parse JSON out of markdown strings** to consume upstream output. `ResolveFindings` uses `re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")` to find findings — fragile and untyped.

## Design

### 1. Dataclass-based structured output

Nodes declare their output shape as a dataclass. The framework auto-generates JSON schema instructions for the prompt and parses the response into typed objects.

Each node defines its own output dataclass — there are no shared types. Nodes are fully independent.

#### Example output dataclasses

```python
from dataclasses import dataclass, field

# In python_code_review.py
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

# In python_test.py — totally different shape
@dataclass
class TestOutput:
    findings: list[dict] = field(
        default_factory=list,
        metadata={"example": [{
            "file": "tests/test_foo.py",
            "line": 10,
            "severity": "HIGH",
            "category": "test_failure",
            "source": "python_test",
            "description": "AssertionError in test_bar.",
            "recommendation": "Fix the off-by-one in foo().",
            "confidence": "high",
        }]},
    )
    summary: dict[str, int] = field(
        default_factory=dict,
        metadata={"example": {
            "tests_run": 50, "tests_passed": 48, "tests_failed": 2,
            "tests_skipped": 0, "tests_xfailed": 0,
            "high": 1, "medium": 1, "low": 0,
        }},
    )
```

No shared base class. Each node owns its shape. This keeps nodes fully independent — adding a field to `TestOutput` can't break `PythonCodeReview`.

#### Schema generation (`agentpipe/schema.py`)

A function `generate_output_instructions(cls) -> str` that:

1. Walks `dataclasses.fields(cls)`
2. Builds a JSON example from `metadata["example"]` values
3. Returns a markdown block appended to the system prompt:

```
## Output

Final reply must be a single fenced JSON block matching this schema and nothing after it:

```json
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH",
      ...
    }
  ],
  "summary": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}
}
```
```

This replaces the hand-written `## Output` section in each node's `_SKILL`. The rest of `_SKILL` (behavior instructions, triage rules, severity guide) stays hand-written because it's node-specific.

If a field has `metadata={"enum": ["HIGH", "MEDIUM", "LOW"]}`, append "One of: HIGH, MEDIUM, LOW" to the field description in the generated output.

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

ResolveFindings doesn't need to know any node's output schema. It serializes whatever typed objects are in state into the prompt for its inner Claude agent:

```python
for key in self._reads_from_keys:
    upstream = state[key]
    if dataclasses.is_dataclass(upstream):
        serialized = json.dumps(dataclasses.asdict(upstream), indent=2)
        parts.append(f"### {key}\n```json\n{serialized}\n```")
    elif isinstance(upstream, str):
        parts.append(f"### {key}\n{upstream}")
```

Claude reads the JSON and interprets it — no duck typing, no shared contracts, no coupling. The inner agent handles whatever structure each upstream node produced.

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

Each node currently has a hand-written `## Output` section in its `_SKILL` string. Migration per node:

1. Define an output dataclass in the node's file (e.g. `ReviewOutput`, `TestOutput`)
2. Remove the `## Output` section from `_SKILL` (keep everything above it — behavior, triage, severity guide)
3. Pass `output=ReviewOutput` to `super().__init__()`
4. The auto-generated schema replaces the hand-written one

Each node's dataclass is independent — no shared types, no imports between nodes.

## Files to create/modify

| File | Change |
|---|---|
| `agentpipe/schema.py` | **New.** `generate_output_instructions()`, `parse_output()` |
| `agentpipe/nodes/base.py` | Add `output` param to `ClaudeAgentNode` and `ShellNode` |
| `agentpipe/nodes/python_code_review.py` | Define `ReviewOutput`, remove `## Output` from `_SKILL`, pass `output=` |
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
- Hand-written `_SKILL` content (behavior, triage, severity guide, exclusions)
- The `_old/` compatibility layer

## Testing

- Unit tests for `generate_output_instructions()` — verify correct JSON examples from dataclass metadata
- Unit tests for `parse_output()` — valid JSON, malformed JSON, missing fields, fenced vs raw JSON
- Unit test: node with `output=` stores a dataclass instance in state
- Unit test: node without `output=` stores raw text (backward compat)
- Unit test: `ResolveFindings` serializes dataclass upstream and falls back to string upstream
- Regression: all existing tests pass unchanged
