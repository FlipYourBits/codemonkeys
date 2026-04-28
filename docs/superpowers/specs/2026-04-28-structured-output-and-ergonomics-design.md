# Structured Output & Pipeline Ergonomics

## Problem

Two friction points in agentpipe's current API:

1. **Every node hand-writes JSON schema instructions** in its system prompt (~30 lines of boilerplate per node, including severity guides). No validation that Claude actually follows the schema.
2. **Downstream nodes regex-parse JSON out of markdown strings** to consume upstream output. `ResolveFindings` uses regex to extract JSON from fenced blocks — fragile and untyped.

## Design

### 1. Pydantic-based structured output

Each node defines a Pydantic `BaseModel` in its own file and passes it to the base class via `output=`. The base class (`ClaudeAgentNode` / `ShellNode`) handles two things automatically:

1. **Prompt generation** — `generate_output_instructions(cls)` reads the model schema (field types, examples, descriptions, Literal constraints) and appends a `## Output` section to the system prompt.
2. **Response parsing** — after the agent responds (or the shell command runs), `parse_output(cls, text)` extracts JSON and validates it via `model.model_validate()`. Stores a typed model instance in state.

There are no shared types. Each node owns its models. Nodes are fully independent.

#### Example output models

```python
from typing import Literal
from pydantic import BaseModel, Field

class CodeReviewFinding(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description=(
            "HIGH: bug that will cause incorrect behavior in production. "
            "MEDIUM: latent bug under specific conditions. "
            "LOW: minor concern worth surfacing but not blocking."
        ),
    )
    category: str = Field(examples=["logic_error"])
    source: str = Field(examples=["python_code_review"])
    description: str = Field(examples=["Off-by-one in loop bound."])
    recommendation: str = Field(examples=["Use < instead of <=."])

class CodeReviewOutput(BaseModel):
    findings: list[CodeReviewFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}],
    )
```

A test node with a completely different shape:

```python
class TestFailure(BaseModel):
    test: str = Field(examples=["tests/test_foo.py::test_bar"])
    error: str = Field(examples=["AssertionError: expected 3, got 4"])
    root_cause: str = Field(examples=["Off-by-one in foo()."])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description=(
            "HIGH: test failure from a bug that affects production. "
            "MEDIUM: edge case regression. "
            "LOW: flaky test or config issue."
        ),
    )

class TestOutput(BaseModel):
    failures: list[TestFailure] = Field(default_factory=list)
    tests_run: int = Field(examples=[50])
    tests_passed: int = Field(examples=[48])
    tests_failed: int = Field(examples=[2])
```

Each node has its own severity descriptions via the `Literal` field's `description`. The allowed values and their meanings are co-located on the field — no separate severity guide section needed.

#### Schema generation (`agentpipe/schema.py`)

A function `generate_output_instructions(cls: type[BaseModel]) -> str` that:

1. Builds a JSON example by walking the model's fields and using `examples` values (or sensible defaults from the type)
2. For `Literal` fields with a `description`, renders the allowed values and their meanings below the example
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
      "category": "logic_error",
      "source": "python_code_review",
      "description": "Off-by-one in loop bound.",
      "recommendation": "Use < instead of <="
    }
  ],
  "summary": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}
}
```

Severity (HIGH | MEDIUM | LOW):
- HIGH: bug that will cause incorrect behavior in production
- MEDIUM: latent bug under specific conditions
- LOW: minor concern worth surfacing but not blocking
```

This replaces the hand-written `## Output` and severity guide in each node's `_SKILL`. The `_SKILL` is reduced to: behavior instructions, triage rules, exclusions.

#### Response parsing (`agentpipe/schema.py`)

A function `parse_output(cls: type[BaseModel], text: str) -> instance | None` that:

1. Extracts JSON from the response (fenced block or raw JSON)
2. Calls `cls.model_validate(data)` — handles nested models, type coercion, and validation automatically
3. Returns `None` on validation failure (logs warning, pipeline continues with raw text)

Pydantic handles all nesting, type checking, and coercion. No custom recursive conversion.

#### Integration with `ClaudeAgentNode`

New optional `output` parameter on `ClaudeAgentNode.__init__`:

```python
class ClaudeAgentNode:
    def __init__(self, *, output: type[BaseModel] | None = None, ...):
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
# Stores either a typed Pydantic model or raw text as fallback
return {self.name: final, "last_cost_usd": tracker.last_cost_usd}
```

#### Integration with `ShellNode`

Same optional `output` parameter. If set, parse stdout as JSON into the model after the command runs:

```python
stdout = result.stdout.strip()
if self.output_cls is not None:
    parsed = parse_output(self.output_cls, stdout)
    if parsed is not None:
        return {self.name: parsed}
return {self.name: stdout}
```

Only ShellNodes that produce JSON stdout use this. `PythonTypeCheck` is the main candidate. `PythonLint`, `PythonFormat`, and `PythonEnsureTools` produce plain text and don't need structured output.

Note: ShellNode `output=` only parses stdout. It does not inject schema into a prompt (there is no prompt — it's a subprocess).

#### Integration with `ResolveFindings`

ResolveFindings handles two upstream formats: Pydantic model instances (new) and raw strings (backward compat).

**Building prior results for the inner Claude agent:**

```python
def _build_prior_results(self, state: dict[str, Any]) -> str:
    parts = ["## Prior results\n"]
    for key in self._reads_from_keys:
        upstream = state.get(key, "")
        if not upstream:
            continue
        if isinstance(upstream, BaseModel):
            serialized = upstream.model_dump_json(indent=2)
            parts.append(f"### {key}\n```json\n{serialized}\n```\n")
        elif isinstance(upstream, str):
            parts.append(f"### {key}\n{upstream}\n")
    return "\n".join(parts) if len(parts) > 1 else ""
```

**Extracting items for the interactive Rich table:**

The interactive flow needs a flat `list[dict]` for the Rich table and user selection. Each upstream model gets dumped to a dict, and we extract any `list` field containing model instances — these are the actionable items:

```python
def _extract_items_from_state(reads_from_keys, state):
    items = []
    for key in reads_from_keys:
        upstream = state.get(key, "")
        if isinstance(upstream, BaseModel):
            data = upstream.model_dump()
            for value in data.values():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    for item in value:
                        item.setdefault("source", key)
                        items.append(item)
        elif isinstance(upstream, str):
            items.extend(_extract_findings(upstream))
    items.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "LOW"), 99))
    return items
```

Scans each upstream model for `list[dict]` fields regardless of field name (`findings`, `failures`, etc.). The Rich table and `_select_by_input` work on this flat list, same as today.

#### Integration with `display.print_results`

`print_results` currently calls `json.loads()` on the resolve_findings output string. Update to handle both:

```python
resolve_output = node_outputs.get("resolve_findings")
if resolve_output is not None:
    if isinstance(resolve_output, BaseModel):
        data = resolve_output.model_dump()
    elif isinstance(resolve_output, str):
        data = json.loads(resolve_output)
    # ... render fixed/skipped from data
```

### 2. Better imports from `agentpipe.nodes`

Export all current node classes from `agentpipe/nodes/__init__.py`:

```python
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_test import PythonTest
from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit
from agentpipe.nodes.python_type_check import PythonTypeCheck
from agentpipe.nodes.python_ensure_tools import PythonEnsureTools
from agentpipe.nodes.docs_review import DocsReview
from agentpipe.nodes.resolve_findings import ResolveFindings
```

One-line import for building a pipeline:

```python
from agentpipe.nodes import PythonLint, PythonTest, PythonCodeReview, ResolveFindings
```

## Migration path for existing nodes

Each node currently has a hand-written `## Output` section and severity guide in its `_SKILL` string. Migration per node:

1. Define Pydantic models in the node's file (e.g. `CodeReviewFinding` + `CodeReviewOutput`) with `Field(examples=..., description=...)` and `Literal` for constrained values
2. Remove the `## Output` and severity guide sections from `_SKILL`
3. Pass `output=CodeReviewOutput` to `super().__init__()`
4. The auto-generated schema replaces the hand-written sections

Each node's models are independent — no shared types, no imports between nodes.

## Dependencies

Add `pydantic` to the core install in `pyproject.toml`:

```toml
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "pydantic>=2.0",
    "rich>=13.0",
]
```

## Files to create/modify

| File | Change |
|---|---|
| `agentpipe/schema.py` | **New.** `generate_output_instructions()`, `parse_output()` |
| `agentpipe/nodes/base.py` | Add `output` param to `ClaudeAgentNode` and `ShellNode` |
| `agentpipe/nodes/python_code_review.py` | Define Pydantic models, remove `## Output` + severity from `_SKILL`, pass `output=` |
| `agentpipe/nodes/python_security_audit.py` | Same pattern |
| `agentpipe/nodes/docs_review.py` | Same pattern |
| `agentpipe/nodes/python_test.py` | Same pattern |
| `agentpipe/nodes/python_dependency_audit.py` | Same pattern |
| `agentpipe/nodes/python_type_check.py` | Define output model, pass `output=` to parse stdout |
| `agentpipe/nodes/resolve_findings.py` | Use `_extract_items_from_state`, `model_dump_json()` for typed upstream, keep regex fallback |
| `agentpipe/display.py` | Handle `BaseModel` instances in `print_results` via `model_dump()` |
| `agentpipe/__init__.py` | Clean up exports |
| `agentpipe/nodes/__init__.py` | Export all current node classes |
| `pyproject.toml` | Add `pydantic>=2.0` to dependencies |

## What this does NOT change

- Node class hierarchy (`ClaudeAgentNode`, `ShellNode`)
- Pipeline topology (`steps`, sequential + parallel via nested lists)
- Permission system (`allow`/`deny`/`on_unmatched`)
- Budget tracking
- Display / verbosity system (Rich table, interactive picker — same UX, different data source)
- Hand-written `_SKILL` content (behavior, method, triage, exclusions)
- The `_old/` compatibility layer

## Testing

- Unit tests for `generate_output_instructions()` — verify JSON example, Literal rendering, severity descriptions
- Unit tests for `parse_output()` — valid JSON, malformed JSON, nested models, fenced vs raw JSON, validation errors
- Unit test: `ClaudeAgentNode` with `output=` appends generated instructions to system prompt
- Unit test: `ShellNode` with `output=` parses JSON stdout into model
- Unit test: node without `output=` stores raw text in state (backward compat)
- Unit test: `_extract_items_from_state` extracts list fields from Pydantic models
- Unit test: `_extract_items_from_state` falls back to regex for string upstream
- Unit test: `display.print_results` handles both BaseModel and string
- Regression: all existing tests pass unchanged
