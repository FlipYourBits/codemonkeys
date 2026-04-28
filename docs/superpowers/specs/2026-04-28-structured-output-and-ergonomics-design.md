# Structured Output & Pipeline Ergonomics

## Problem

Two friction points in agentpipe's current API:

1. **Every node hand-writes JSON schema instructions** in its system prompt (~30 lines of boilerplate per node, including severity guides). No validation that Claude actually follows the schema.
2. **Downstream nodes regex-parse JSON out of markdown strings** to consume upstream output. `ResolveFindings` uses regex to extract JSON from fenced blocks — fragile and untyped.

## Design

### 1. Dataclass-based structured output

Each node defines an output dataclass in its own file and passes it to the base class via `output=`. The base class (`ClaudeAgentNode` / `ShellNode`) handles two things automatically:

1. **Prompt generation** — appends a `## Output` section to the system prompt with JSON schema, examples, and severity descriptions, all derived from the dataclass's `field(metadata=...)`.
2. **Response parsing** — after the agent responds (or the shell command runs), parses the output into a typed dataclass instance and stores it in state.

There are no shared types. Each node owns its dataclass. Nodes are fully independent.

#### Dataclass constraints

Fields must use simple JSON-serializable types only: `str`, `int`, `float`, `bool`, `list[dict]`, `dict[str, ...]`. No nested dataclasses — keeps `parse_output` dead simple (`cls(**data)`, no recursive conversion).

#### Example output dataclasses

Each node defines whatever shape makes sense:

```python
from dataclasses import dataclass, field

# Review node — reports issues with severity
@dataclass
class CodeReviewOutput:
    findings: list[dict] = field(
        default_factory=list,
        metadata={
            "example": [{
                "file": "path/to/file.py",
                "line": 42,
                "severity": "HIGH",
                "category": "logic_error",
                "source": "python_code_review",
                "description": "Off-by-one in loop bound.",
                "recommendation": "Use < instead of <=.",
            }],
            "severity_guide": {
                "HIGH": "Bug that will cause incorrect behavior in production",
                "MEDIUM": "Latent bug under specific conditions",
                "LOW": "Minor concern worth surfacing but not blocking",
            },
        },
    )
    summary: dict[str, int] = field(
        default_factory=dict,
        metadata={"example": {"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}},
    )

# Test node — different shape entirely
@dataclass
class TestOutput:
    failures: list[dict] = field(
        default_factory=list,
        metadata={
            "example": [{
                "test": "tests/test_foo.py::test_bar",
                "error": "AssertionError: expected 3, got 4",
                "root_cause": "Off-by-one in foo().",
            }],
        },
    )
    tests_run: int = field(metadata={"example": 50})
    tests_passed: int = field(metadata={"example": 48})
    tests_failed: int = field(metadata={"example": 2})
```

Fields with constrained values use `severity_guide` in metadata. `generate_output_instructions` renders these into the prompt. `dataclasses.asdict()` ignores all metadata — it never appears in output.

#### Schema generation (`agentpipe/schema.py`)

A function `generate_output_instructions(cls) -> str` that:

1. Walks `dataclasses.fields(cls)`
2. Builds a JSON example from `metadata["example"]` values
3. If any field has `metadata["severity_guide"]`, appends a severity section:
   ```
   Severity:
   - HIGH: Bug that will cause incorrect behavior in production
   - MEDIUM: Latent bug under specific conditions
   - LOW: Minor concern worth surfacing but not blocking
   ```
4. Returns a complete markdown block:
   ```
   ## Output

   Final reply must be a single fenced JSON block matching this schema and nothing after it:

   ```json
   { ... example ... }
   ```

   Severity:
   - HIGH: ...
   - MEDIUM: ...
   - LOW: ...
   ```

This replaces the hand-written `## Output` and severity guide in each node's `_SKILL`. The `_SKILL` is reduced to: behavior instructions, triage rules, exclusions.

#### Response parsing (`agentpipe/schema.py`)

A function `parse_output(cls, text: str) -> instance | None` that:

1. Extracts JSON from the response (fenced block or raw JSON)
2. Converts the dict to the dataclass via `cls(**data)`
3. Returns `None` on failure (malformed JSON, missing required fields)

No external dependencies — stdlib `dataclasses` + `json`. ~30-40 lines. No recursive conversion needed because fields are restricted to simple types (no nested dataclasses).

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

Only ShellNodes that produce JSON stdout use this. `PythonTypeCheck` is the main candidate — its embedded script already outputs JSON. `PythonLint`, `PythonFormat`, and `PythonEnsureTools` produce plain text and don't need structured output.

Note: ShellNode `output=` does NOT inject schema into a prompt (there's no prompt). It only parses stdout. The command itself is responsible for producing compatible JSON.

#### Integration with `ResolveFindings`

ResolveFindings needs to handle two upstream formats: dataclass instances (new) and raw strings (backward compat / nodes without `output=`).

**Building prior results for the inner Claude agent:**

```python
import dataclasses

def _build_prior_results(self, state: dict[str, Any]) -> str:
    parts = ["## Prior results\n"]
    for key in self._reads_from_keys:
        upstream = state.get(key, "")
        if not upstream:
            continue
        if dataclasses.is_dataclass(upstream):
            serialized = json.dumps(dataclasses.asdict(upstream), indent=2)
            parts.append(f"### {key}\n```json\n{serialized}\n```\n")
        elif isinstance(upstream, str):
            parts.append(f"### {key}\n{upstream}\n")
    return "\n".join(parts) if len(parts) > 1 else ""
```

**Extracting items for the interactive Rich table and selection:**

The interactive flow needs a flat `list[dict]` for `_format_findings` (Rich table) and `_select_by_input` (user picks by number/severity). Each upstream dataclass gets serialized to a dict, and we look for any `list[dict]` field that contains items — these are the actionable items to display:

```python
def _extract_items_from_state(reads_from_keys, state):
    """Extract actionable items from upstream state for interactive display."""
    items = []
    for key in reads_from_keys:
        upstream = state.get(key, "")
        if dataclasses.is_dataclass(upstream):
            data = dataclasses.asdict(upstream)
            for field_name, value in data.items():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    for item in value:
                        item.setdefault("source", key)
                        items.append(item)
        elif isinstance(upstream, str):
            # Fallback: regex extraction for raw string output
            items.extend(_extract_findings(upstream))
    items.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "LOW"), 99))
    return items
```

This scans each upstream dataclass for `list[dict]` fields (e.g. `findings`, `failures`, `issues` — whatever the node named them) and flattens into a single list. The Rich table and selection logic work on this flat list, same as today.

**Why this works regardless of field names:** The extraction doesn't look for a specific field name. It finds any `list[dict]` field in the dataclass. A code review node with `findings: list[dict]` and a test node with `failures: list[dict]` both contribute to the same flat list.

**Display of the items in the Rich table** uses `.get()` on each dict, so missing fields just show "?" — a `TestOutput` failure dict without a `severity` field still renders, just without color-coding.

#### Integration with `display.print_results`

`display.print_results` currently calls `json.loads(resolve_output)` assuming a string. After this change, `node_outputs` may contain dataclass instances. Update `print_results` to handle both:

```python
resolve_output = node_outputs.get("resolve_findings")
if resolve_output is not None:
    if dataclasses.is_dataclass(resolve_output):
        data = dataclasses.asdict(resolve_output)
    elif isinstance(resolve_output, str):
        data = json.loads(resolve_output)
    # ... render fixed/skipped from data
```

Note: `ResolveFindings` inner fixer output is still parsed by the fixer's own `output=` if set, or stored as raw text. Either way, `display.print_results` handles both forms.

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

1. Define an output dataclass in the node's file with whatever fields make sense, using `metadata["example"]` for examples and `metadata["severity_guide"]` for severity descriptions where applicable
2. Remove the `## Output` and severity guide sections from `_SKILL`
3. Pass `output=MyOutput` to `super().__init__()`
4. The auto-generated schema replaces the hand-written sections

Each node's dataclass is independent — no shared types, no imports between nodes.

## Files to create/modify

| File | Change |
|---|---|
| `agentpipe/schema.py` | **New.** `generate_output_instructions()`, `parse_output()` |
| `agentpipe/nodes/base.py` | Add `output` param to `ClaudeAgentNode` and `ShellNode` |
| `agentpipe/nodes/python_code_review.py` | Define output dataclass, remove `## Output` + severity from `_SKILL`, pass `output=` |
| `agentpipe/nodes/python_security_audit.py` | Same pattern |
| `agentpipe/nodes/docs_review.py` | Same pattern |
| `agentpipe/nodes/python_test.py` | Same pattern |
| `agentpipe/nodes/python_dependency_audit.py` | Same pattern |
| `agentpipe/nodes/python_type_check.py` | Define output dataclass, pass `output=` to parse stdout |
| `agentpipe/nodes/resolve_findings.py` | Use `_extract_items_from_state` for typed upstream, keep `_extract_findings` regex fallback for strings |
| `agentpipe/display.py` | Handle dataclass instances in `print_results` via `dataclasses.asdict()` |
| `agentpipe/__init__.py` | Clean up exports |
| `agentpipe/nodes/__init__.py` | Export all current node classes |

## What this does NOT change

- Node class hierarchy (`ClaudeAgentNode`, `ShellNode`)
- Pipeline topology (`steps`, sequential + parallel via nested lists)
- Permission system (`allow`/`deny`/`on_unmatched`)
- Budget tracking
- Display / verbosity system (Rich table, interactive picker — same UX, different data source)
- Hand-written `_SKILL` content (behavior, method, triage, exclusions)
- The `_old/` compatibility layer

## Testing

- Unit tests for `generate_output_instructions()` — verify correct JSON examples and severity guide from dataclass metadata
- Unit tests for `parse_output()` — valid JSON, malformed JSON, missing fields, fenced vs raw JSON
- Unit test: `ClaudeAgentNode` with `output=` appends generated instructions to system prompt
- Unit test: `ShellNode` with `output=` parses JSON stdout into dataclass
- Unit test: node without `output=` stores raw text in state (backward compat)
- Unit test: `_extract_items_from_state` pulls `list[dict]` fields from dataclass instances
- Unit test: `_extract_items_from_state` falls back to regex for string upstream
- Unit test: `display.print_results` handles both dataclass and string resolve_findings output
- Regression: all existing tests pass unchanged
