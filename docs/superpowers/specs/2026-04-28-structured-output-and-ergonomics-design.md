# Structured Output & Pipeline Ergonomics

## Problem

Three friction points in agentpipe's current API:

1. **Every node hand-writes JSON schema instructions** in its system prompt (~30 lines of boilerplate per node). No validation that Claude actually follows the schema.
2. **Downstream nodes regex-parse JSON out of markdown strings** to consume upstream output. `ResolveFindings` uses `re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")` to find findings — fragile and untyped.
3. **`parallel()` is missing** — nested lists work but aren't self-documenting.

## Design

### 1. Dataclass-based structured output

Nodes declare their output shape as a dataclass. The framework auto-generates JSON schema instructions for the prompt and parses the response into typed objects.

#### Shared types (`agentpipe/types.py`)

```python
from dataclasses import dataclass, field

@dataclass
class Finding:
    file: str = field(metadata={"example": "path/to/file.py"})
    line: int = field(metadata={"example": 42})
    severity: str = field(metadata={"example": "HIGH", "enum": ["HIGH", "MEDIUM", "LOW"]})
    category: str = field(metadata={"example": "logic_error"})
    source: str = field(metadata={"example": "python_code_review"})
    description: str = field(metadata={"example": "Off-by-one in loop bound."})
    recommendation: str = field(metadata={"example": "Use < instead of <=."})
    confidence: str = field(metadata={"example": "high", "enum": ["high", "medium", "low"]})
```

`Finding` is the contract between "nodes that report issues" and "nodes that fix issues." It lives in `agentpipe.types`, not in any node.

Each node defines its own output dataclass that uses `Finding`:

```python
@dataclass
class ReviewOutput:
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, int] = field(
        default_factory=dict,
        metadata={"example": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}},
    )
```

#### Schema generation (`agentpipe/schema.py`)

A single function `generate_output_instructions(cls) -> str` that:

1. Walks `dataclasses.fields(cls)` recursively
2. Builds a JSON example from `metadata["example"]` values
3. Returns a markdown block:

```
## Output

Final reply must be a single fenced JSON block matching this schema and nothing after it:

```json
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      ...
    }
  ],
  "summary": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}
}
```

If there are no findings, return an empty `findings` array.
```

This replaces the hand-written output sections in every node's `_SKILL` constant.

#### Response parsing (`agentpipe/schema.py`)

A function `parse_output(cls, text: str) -> instance | None` that:

1. Extracts JSON from the response (fenced block or raw)
2. Recursively converts the dict to the dataclass (handling `list[Finding]`, nested dataclasses, etc.)
3. Returns `None` on failure (malformed JSON, missing fields)

No external dependencies — `dataclasses.fields()` + recursive dict-to-dataclass conversion is ~40 lines.

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
if self.output_cls is not None:
    parsed = parse_output(self.output_cls, final)
    if parsed is not None:
        final = parsed
# Store in state — either the parsed dataclass or raw text as fallback
return {self.name: final, "last_cost_usd": tracker.last_cost_usd}
```

#### Integration with `ShellNode`

Same `output` parameter. If set, parse stdout as JSON into the dataclass:

```python
if self.output_cls is not None:
    parsed = parse_output(self.output_cls, result.stdout.strip())
    if parsed is not None:
        return {self.name: parsed}
return {self.name: result.stdout.strip()}
```

This lets `PythonTypeCheck` drop its embedded `_MYPY_SCRIPT` JSON generation and use a standard output dataclass instead. Actually — `PythonTypeCheck` runs mypy and transforms its output into our findings format via that script. The script still needs to exist because mypy's output format isn't our `Finding` format. But the ShellNode `output` param would parse the script's JSON stdout into a typed `TypeCheckOutput` dataclass instead of storing raw text.

#### Integration with `ResolveFindings`

ResolveFindings stops regex-parsing. It reads typed objects from state via duck typing:

```python
for key in self._reads_from_keys:
    upstream = state[key]
    if hasattr(upstream, "findings"):
        all_findings.extend(upstream.findings)
    # Fallback: if upstream is still a string (no output schema), use current regex parser
    elif isinstance(upstream, str):
        all_findings.extend(_extract_findings_from_text(key, upstream))
```

The fallback keeps backward compat with any node that doesn't use `output=`.

### 2. `parallel()` helper

Replace nested-list convention with an explicit function.

```python
# agentpipe/__init__.py
def parallel(*nodes):
    """Mark nodes for concurrent execution in a Pipeline step."""
    return list(nodes)
```

That's it — one line. `Pipeline._resolve_step` already handles lists. The difference is purely readability:

```python
# Before:
steps=[lint, [test, review, security], resolve]

# After:
steps=[lint, parallel(test, review, security), resolve]
```

Drop support for bare nested lists — `parallel()` is the only way. This is a single change in `Pipeline._resolve_step`: raise `TypeError` if a step is a `list` that wasn't created by `parallel()`. Simplest approach: `parallel()` returns a thin wrapper (a `Parallel` namedtuple or similar) instead of a plain list, and `_resolve_step` checks for that type.

### 3. Better imports from `agentpipe.nodes`

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

Each node currently has a hand-written output section in its `_SKILL` string. Migration per node:

1. Define a `*Output` dataclass (e.g. `ReviewOutput`, `SecurityOutput`, `TestOutput`) — most reuse `Finding` with different `summary` fields
2. Remove the `## Output` section from `_SKILL`
3. Pass `output=ReviewOutput` to `super().__init__()`
4. The auto-generated schema replaces the hand-written one

Nodes that share the same output shape (code review, security audit, docs review) can share one `ReviewOutput` class or define minimal subclasses.

## Files to create/modify

| File | Change |
|---|---|
| `agentpipe/types.py` | **New.** `Finding` dataclass, shared output types |
| `agentpipe/schema.py` | **New.** `generate_output_instructions()`, `parse_output()` |
| `agentpipe/nodes/base.py` | Add `output` param to `ClaudeAgentNode` and `ShellNode` |
| `agentpipe/nodes/python_code_review.py` | Define `ReviewOutput`, remove hand-written `## Output` from `_SKILL`, pass `output=` |
| `agentpipe/nodes/python_security_audit.py` | Same pattern |
| `agentpipe/nodes/docs_review.py` | Same pattern |
| `agentpipe/nodes/python_test.py` | Define `TestOutput`, same pattern |
| `agentpipe/nodes/python_dependency_audit.py` | Define `AuditOutput`, same pattern |
| `agentpipe/nodes/python_type_check.py` | Define `TypeCheckOutput`, parse stdout |
| `agentpipe/nodes/resolve_findings.py` | Read `.findings` from typed state, fallback to regex for untyped |
| `agentpipe/__init__.py` | Add `parallel()`, export new types |
| `agentpipe/nodes/__init__.py` | Export all node classes |
| `agentpipe/pipeline.py` | Use `Parallel` type instead of bare `list` check |

## What this does NOT change

- Node class hierarchy (`ClaudeAgentNode`, `ShellNode`)
- Pipeline topology (`steps`, sequential + parallel)
- Permission system (`allow`/`deny`/`on_unmatched`)
- Budget tracking
- Display / verbosity system
- `_SKILL` system prompt pattern — only the `## Output` section gets auto-generated
- The `_old/` compatibility layer

## Testing

- Unit tests for `generate_output_instructions()` — verify it produces correct JSON examples from dataclass fields
- Unit tests for `parse_output()` — valid JSON, malformed JSON, missing fields, nested dataclasses
- Integration test: a node with `output=ReviewOutput` stores a `ReviewOutput` instance in state
- Integration test: `ResolveFindings` reads `.findings` from typed upstream nodes
- Regression: existing tests continue to pass (fallback to raw text when `output` is not set)
