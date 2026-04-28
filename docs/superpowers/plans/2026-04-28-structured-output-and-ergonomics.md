# Structured Output & Pipeline Ergonomics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-written JSON schema prompts and regex parsing with Pydantic-based structured output — each node defines a `BaseModel`, the base class auto-generates prompt instructions and validates responses.

**Architecture:** New `agentpipe/schema.py` provides two functions: `generate_output_instructions(cls)` builds a `## Output` prompt section from any Pydantic model, and `parse_output(cls, text)` extracts + validates JSON from agent responses. `ClaudeAgentNode` and `ShellNode` get an `output=` parameter that wires these in automatically. Each node defines its own Pydantic models — no shared types.

**Tech Stack:** Pydantic v2, Python 3.10+, pytest, pytest-asyncio

---

### Task 1: Add pydantic dependency

**Files:**
- Modify: `pyproject.toml:22-25`

- [ ] **Step 1: Add pydantic to dependencies**

In `pyproject.toml`, add `pydantic>=2.0,<3` to the `dependencies` list:

```toml
dependencies = [
    "claude-agent-sdk>=0.1.0,<1.0",
    "pydantic>=2.0,<3",
    "rich>=13.0,<14",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `.venv/bin/python -m pip install -e ".[dev]"`
Expected: installs pydantic alongside existing deps

- [ ] **Step 3: Verify pydantic importable**

Run: `.venv/bin/python -c "import pydantic; print(pydantic.__version__)"`
Expected: prints 2.x version

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add pydantic>=2.0"
```

---

### Task 2: Create `agentpipe/schema.py` — `generate_output_instructions`

**Files:**
- Create: `agentpipe/schema.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests for `generate_output_instructions`**

Create `tests/test_schema.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TestGenerateOutputInstructions:
    def test_simple_model_has_json_example(self):
        from agentpipe.schema import generate_output_instructions

        class Output(BaseModel):
            name: str = Field(examples=["Alice"])
            count: int = Field(examples=[42])

        result = generate_output_instructions(Output)
        assert "## Output" in result
        assert '"name": "Alice"' in result
        assert '"count": 42' in result
        assert "```json" in result

    def test_literal_field_renders_allowed_values(self):
        from agentpipe.schema import generate_output_instructions

        class Output(BaseModel):
            severity: Literal["HIGH", "LOW"] = Field(
                description="HIGH: critical. LOW: minor."
            )

        result = generate_output_instructions(Output)
        assert "HIGH" in result
        assert "LOW" in result
        assert "critical" in result
        assert "minor" in result

    def test_nested_model_renders_example(self):
        from agentpipe.schema import generate_output_instructions

        class Item(BaseModel):
            file: str = Field(examples=["a.py"])
            line: int = Field(examples=[10])

        class Output(BaseModel):
            items: list[Item] = Field(default_factory=list)

        result = generate_output_instructions(Output)
        assert '"file": "a.py"' in result
        assert '"line": 10' in result

    def test_dict_field_with_example(self):
        from agentpipe.schema import generate_output_instructions

        class Output(BaseModel):
            summary: dict[str, int] = Field(
                default_factory=dict,
                examples=[{"total": 5, "passed": 4}],
            )

        result = generate_output_instructions(Output)
        assert '"total": 5' in result or '"passed": 4' in result

    def test_field_without_examples_uses_type_default(self):
        from agentpipe.schema import generate_output_instructions

        class Output(BaseModel):
            name: str
            count: int
            flag: bool

        result = generate_output_instructions(Output)
        assert '"name"' in result
        assert '"count"' in result
        assert '"flag"' in result

    def test_multiple_literal_fields_each_rendered(self):
        from agentpipe.schema import generate_output_instructions

        class Output(BaseModel):
            severity: Literal["HIGH", "LOW"] = Field(
                description="HIGH: bad. LOW: ok."
            )
            confidence: Literal["high", "medium", "low"] = Field(
                description="high: sure. medium: maybe. low: guess."
            )

        result = generate_output_instructions(Output)
        assert "severity" in result.lower() or "Severity" in result
        assert "confidence" in result.lower() or "Confidence" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py -x -q --no-header`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentpipe.schema'`

- [ ] **Step 3: Implement `generate_output_instructions`**

Create `agentpipe/schema.py`:

```python
"""Pydantic-based structured output: prompt generation and response parsing."""

from __future__ import annotations

import json
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _type_default(tp: type) -> Any:
    if tp is str:
        return "..."
    if tp is int:
        return 0
    if tp is float:
        return 0.0
    if tp is bool:
        return True
    return "..."


def _example_value(field_name: str, field_info: FieldInfo, annotation: Any) -> Any:
    examples = (
        field_info.examples
        if hasattr(field_info, "examples") and field_info.examples
        else None
    )

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Literal:
        return args[0] if args else "..."

    if origin is list:
        if args and _is_model(args[0]):
            return [_build_example(args[0])]
        if examples:
            return examples[0] if isinstance(examples[0], list) else [examples[0]]
        return []

    if origin is dict:
        if examples:
            return examples[0] if isinstance(examples[0], dict) else {}
        return {}

    if _is_model(annotation):
        return _build_example(annotation)

    if examples:
        return examples[0]

    return _type_default(annotation if isinstance(annotation, type) else type(annotation) if not isinstance(annotation, type) else str)


def _is_model(tp: Any) -> bool:
    try:
        return isinstance(tp, type) and issubclass(tp, BaseModel)
    except TypeError:
        return False


def _build_example(cls: type[BaseModel]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, field_info in cls.model_fields.items():
        result[name] = _example_value(name, field_info, field_info.annotation)
    return result


def _collect_literal_descriptions(cls: type[BaseModel]) -> list[tuple[str, list[str], str]]:
    descriptions: list[tuple[str, list[str], str]] = []
    for name, field_info in cls.model_fields.items():
        origin = get_origin(field_info.annotation)
        if origin is Literal and field_info.description:
            values = list(get_args(field_info.annotation))
            descriptions.append((name, [str(v) for v in values], field_info.description))
    return descriptions


def generate_output_instructions(cls: type[BaseModel]) -> str:
    example = _build_example(cls)
    example_json = json.dumps(example, indent=2)

    parts = [
        "## Output",
        "",
        "Final reply must be a single fenced JSON block matching this schema and nothing after it:",
        "",
        "```json",
        example_json,
        "```",
    ]

    for field_name, values, description in _collect_literal_descriptions(cls):
        label = field_name.replace("_", " ").title()
        parts.append("")
        parts.append(f"{label} ({' | '.join(values)}):")
        for sentence in description.replace(". ", ".\n").split("\n"):
            sentence = sentence.strip()
            if not sentence:
                continue
            for value in values:
                if sentence.startswith(f"{value}:"):
                    parts.append(f"- {sentence}")
                    break

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema.py -x -q --no-header`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/schema.py tests/test_schema.py
git commit -m "feat: generate_output_instructions from Pydantic models"
```

---

### Task 3: Add `parse_output` to `agentpipe/schema.py`

**Files:**
- Modify: `agentpipe/schema.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests for `parse_output`**

Append to `tests/test_schema.py`:

```python
import pytest


class TestParseOutput:
    def test_parses_fenced_json(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            name: str
            count: int

        text = 'Here is the result:\n\n```json\n{"name": "Alice", "count": 5}\n```'
        result = parse_output(Output, text)
        assert result.name == "Alice"
        assert result.count == 5

    def test_parses_raw_json(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            value: int

        text = '{"value": 42}'
        result = parse_output(Output, text)
        assert result.value == 42

    def test_parses_nested_model(self):
        from agentpipe.schema import parse_output

        class Item(BaseModel):
            name: str

        class Output(BaseModel):
            items: list[Item]

        text = '```json\n{"items": [{"name": "a"}, {"name": "b"}]}\n```'
        result = parse_output(Output, text)
        assert len(result.items) == 2
        assert result.items[0].name == "a"

    def test_raises_on_no_json(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            value: int

        with pytest.raises(ValueError, match="No JSON"):
            parse_output(Output, "no json here at all")

    def test_raises_on_invalid_json(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            value: int

        with pytest.raises(ValueError):
            parse_output(Output, '```json\n{invalid}\n```')

    def test_raises_on_validation_error(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            value: int

        with pytest.raises(ValueError):
            parse_output(Output, '{"value": "not_a_number"}')

    def test_handles_text_before_and_after_json(self):
        from agentpipe.schema import parse_output

        class Output(BaseModel):
            x: int

        text = "Some analysis here.\n\n```json\n{\"x\": 7}\n```\n\nDone."
        result = parse_output(Output, text)
        assert result.x == 7
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestParseOutput -x -q --no-header`
Expected: FAIL — `ImportError: cannot import name 'parse_output'`

- [ ] **Step 3: Implement `parse_output`**

Add to `agentpipe/schema.py`:

```python
import re

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n([\s\S]*?)\n\s*```")


def parse_output(cls: type[BaseModel], text: str) -> BaseModel:
    match = _JSON_FENCE_RE.search(text)
    if match:
        raw = match.group(1)
    else:
        raw = text.strip()
        if not raw.startswith("{"):
            raise ValueError(f"No JSON found in response for {cls.__name__}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for {cls.__name__}: {e}") from e

    try:
        return cls.model_validate(data)
    except Exception as e:
        raise ValueError(f"Validation failed for {cls.__name__}: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema.py -x -q --no-header`
Expected: all 13 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add agentpipe/schema.py tests/test_schema.py
git commit -m "feat: parse_output extracts and validates JSON from responses"
```

---

### Task 4: Add `output=` parameter to `ClaudeAgentNode`

**Files:**
- Modify: `agentpipe/nodes/base.py:165-302`
- Modify: `tests/test_base_unit.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_base_unit.py`:

```python
from pydantic import BaseModel, Field


class TestClaudeAgentNodeOutput:
    def test_output_appends_instructions_to_system_prompt(self):
        class MyOutput(BaseModel):
            value: int = Field(examples=[42])

        node = ClaudeAgentNode(name="t", output=MyOutput)
        assert "## Output" in node.system_prompt
        assert "42" in node.system_prompt

    def test_no_output_leaves_system_prompt_unchanged(self):
        node = ClaudeAgentNode(name="t", system_prompt="base")
        assert "## Output" not in node.system_prompt
        assert node.system_prompt == "base"

    def test_output_cls_stored(self):
        class MyOutput(BaseModel):
            x: int

        node = ClaudeAgentNode(name="t", output=MyOutput)
        assert node.output_cls is MyOutput

    def test_no_output_cls_is_none(self):
        node = ClaudeAgentNode(name="t")
        assert node.output_cls is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_base_unit.py::TestClaudeAgentNodeOutput -x -q --no-header`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'output'`

- [ ] **Step 3: Add `output` parameter to `ClaudeAgentNode.__init__`**

In `agentpipe/nodes/base.py`, add the import at the top (after the existing imports):

```python
from pydantic import BaseModel as _BaseModel
```

Modify `ClaudeAgentNode.__init__` signature to add the `output` parameter after `system_prompt`:

```python
    def __init__(
        self,
        *,
        name: str,
        display_name: str | None = None,
        system_prompt: str = "",
        output: type[_BaseModel] | None = None,
        skills: Sequence[str | Path] = (),
        ...  # rest unchanged
```

Add these lines at the end of `__init__`, after the existing `self.declared_outputs` assignment:

```python
        self.output_cls: type[_BaseModel] | None = output
        if output is not None:
            from agentpipe.schema import generate_output_instructions
            self.system_prompt += "\n\n" + generate_output_instructions(output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_base_unit.py::TestClaudeAgentNodeOutput -x -q --no-header`
Expected: all 4 tests PASS

- [ ] **Step 5: Add `parse_output` call in `ClaudeAgentNode.__call__`**

In `ClaudeAgentNode.__call__`, replace the final return block (lines ~298-302):

```python
        final = result_text if result_text else "\n".join(text_chunks).strip()
        if self.output_cls is not None:
            from agentpipe.schema import parse_output
            final = parse_output(self.output_cls, final)
        return {
            self.name: final,
            "last_cost_usd": tracker.last_cost_usd,
        }
```

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass (no existing node uses `output=` yet)

- [ ] **Step 7: Commit**

```bash
git add agentpipe/nodes/base.py tests/test_base_unit.py
git commit -m "feat: ClaudeAgentNode output= param for structured output"
```

---

### Task 5: Add `output=` parameter to `ShellNode`

**Files:**
- Modify: `agentpipe/nodes/base.py:305-395`
- Modify: `tests/test_base_unit.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_base_unit.py`:

```python
class TestShellNodeOutput:
    def test_output_parses_json_stdout(self):
        class MyOutput(BaseModel):
            value: int

        node = ShellNode(name="t", command='echo \'{"value": 42}\'', output=MyOutput)
        result = asyncio.run(node({"working_dir": None}))
        assert hasattr(result["t"], "value")
        assert result["t"].value == 42

    def test_no_output_returns_raw_string(self):
        node = ShellNode(name="t", command="echo hello")
        result = asyncio.run(node({"working_dir": None}))
        assert result["t"] == "hello"

    def test_output_cls_stored(self):
        class MyOutput(BaseModel):
            x: int

        node = ShellNode(name="t", command="true", output=MyOutput)
        assert node.output_cls is MyOutput

    def test_no_output_cls_is_none(self):
        node = ShellNode(name="t", command="true")
        assert node.output_cls is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_base_unit.py::TestShellNodeOutput -x -q --no-header`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'output'`

- [ ] **Step 3: Add `output` parameter to `ShellNode`**

In `ShellNode.__init__`, add the `output` parameter:

```python
    def __init__(
        self,
        *,
        name: str,
        command: str | list[str] | Callable[[dict[str, Any]], str | list[str]],
        output: type[_BaseModel] | None = None,
        check: bool = True,
        timeout: float | None = None,
        verbosity: Verbosity = Verbosity.silent,
    ) -> None:
        self.name = name
        self.command = command
        self.output_cls: type[_BaseModel] | None = output
        self.check = check
        ...
```

In `ShellNode.__call__`, for the silent branch, replace `return {self.name: result.stdout.strip()}` with:

```python
            stdout = result.stdout.strip()
            if self.output_cls is not None:
                from agentpipe.schema import parse_output
                return {self.name: parse_output(self.output_cls, stdout)}
            return {self.name: stdout}
```

For the verbose branch, replace `return {self.name: "".join(stdout_chunks).strip()}` with:

```python
        stdout = "".join(stdout_chunks).strip()
        if self.output_cls is not None:
            from agentpipe.schema import parse_output
            return {self.name: parse_output(self.output_cls, stdout)}
        return {self.name: stdout}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_base_unit.py::TestShellNodeOutput -x -q --no-header`
Expected: all 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add agentpipe/nodes/base.py tests/test_base_unit.py
git commit -m "feat: ShellNode output= param for structured output"
```

---

### Task 6: Migrate `PythonCodeReview` to Pydantic output

**Files:**
- Modify: `agentpipe/nodes/python_code_review.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test for the node's output model**

Append to `tests/test_schema.py`:

```python
class TestCodeReviewModels:
    def test_code_review_output_validates(self):
        from agentpipe.nodes.python_code_review import CodeReviewOutput

        data = {
            "findings": [
                {
                    "file": "a.py",
                    "line": 42,
                    "severity": "HIGH",
                    "category": "logic_error",
                    "source": "python_code_review",
                    "description": "Bug.",
                    "recommendation": "Fix it.",
                    "confidence": "high",
                }
            ],
            "summary": {"files_reviewed": 1, "high": 1, "medium": 0, "low": 0},
        }
        output = CodeReviewOutput.model_validate(data)
        assert len(output.findings) == 1
        assert output.findings[0].severity == "HIGH"

    def test_code_review_node_has_output_instructions(self):
        from agentpipe.nodes.python_code_review import PythonCodeReview

        node = PythonCodeReview()
        assert "## Output" in node.system_prompt
        assert "severity" in node.system_prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestCodeReviewModels -x -q --no-header`
Expected: FAIL — `ImportError: cannot import name 'CodeReviewOutput'`

- [ ] **Step 3: Define Pydantic models and wire `output=`**

Replace the entire `agentpipe/nodes/python_code_review.py` with:

```python
"""Semantic code review of Python source."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentpipe.models import OPUS_4_6
from agentpipe.nodes.base import ClaudeAgentNode

_SKILL = """\
# Code review

Semantic code review focused on correctness,
maintainability, and design quality. You review things
that linters, formatters, type-checkers, and test runners
cannot catch — those tools run in separate pipeline nodes.
Do not run them.

Report findings only — do not fix issues.

## Source Code Only

Only analyze Python source files. Skip configuration,
generated files, lock files, documentation, and vendored
dependencies. Files to SKIP: `poetry.lock`, `*.pyc`,
`*.egg-info/`, `__pycache__/`, `.venv/`, `dist/`,
`*.generated.*`, `*.md`, `*.rst`.

## Scope

{scope_section}

## Method

{method_intro} Look for issues in these categories. Only
report when you're confident a real problem exists.

### `logic_error`
- Off-by-one bounds, wrong comparison operator
- Swapped arguments to a function
- Broken control flow — early `return` inside a loop that
  should `continue`, missing `else` branch
- Wrong default value that changes semantics
- Negation errors (`if not x` when `x` is meant)
- Mutable default argument (`def f(x=[])`) — shared across
  calls
- Late-binding closure in a loop (`lambda: i` captures the
  variable, not the value)
- Using `is` / `is not` for value comparison instead of
  `==` / `!=` (or vice versa for singletons)
- `__eq__` defined without `__hash__` — breaks dict/set
  behavior
- Mutable class attribute shared across all instances when
  per-instance state was intended

### `complexity`
- Functions longer than ~50 lines — suggest extracting a
  helper
- Deeply nested conditionals (3+ levels) — suggest early
  returns or extraction
- God classes / modules that do too many unrelated things
- Complex boolean expressions that should be named or
  broken up

### `error_handling`
- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging or re-raising
- Missing error path on a fallible operation (file read,
  network, parse)
- Try/except block that's too wide — masks unrelated errors

### `resource_leak`
- File or connection opened without a context manager
- Subprocess started without ensuring termination
- `asyncio` task created without awaiting or cancelling
- Thread pool / executor not shut down (use `with` or
  explicit `.shutdown()`)

### `concurrency`
- Shared mutable state without synchronization
- Missing `await` on an async call
- Race between check and use (TOCTOU) — but NOT
  security-sensitive TOCTOU (security audit owns those)
- Deadlock potential — locks acquired in different orders

### `performance`
- Quadratic loops over data that could be set-indexed
- N+1 database queries in a loop
- Repeated computation that could be hoisted
- Loading entire collection into memory when a generator
  would do

### `api_contract`
- Breaking change to a public signature with no version
  bump or migration note
- Function renamed but old name not deprecated
- Inconsistent return types across code paths (e.g.,
  returns a value on success but `None` on failure with no
  `Optional` annotation or documented intent)

### `dead_code`
- Code branch that can never execute given the conditions
  before it
- Function/import that became unused after the diff
- Commented-out blocks left behind

### `clarity` (high bar — only flag when clearly wrong)
- Misleading name (function does X but is named Y)
- Magic number where a named constant would prevent a bug
- Duplicated logic that's drifted between copies

## Triage

- Only report findings you would flag in a real code
  review. If you're not sure, leave it out.
- Drop anything where you can't articulate a concrete
  failure mode.
- Deduplicate — keep the finding with the strongest
  evidence.
- Cap at 15 findings. If you have more, keep the highest
  severity and confidence ones.

## Exclusions — DO NOT REPORT

- Formatting / whitespace / import order (formatters own
  these)
- Type errors, missing type annotations (type-checkers
  own these)
- Lint violations (linters own these)
- Missing tests or test failures (test node owns these)
- Security vulnerabilities (security audit owns these)
- Docstring accuracy (docs review owns these)
- Naming preferences without a misleading-name argument
- "I would have written this differently" without a
  correctness argument
- Performance issues with no measurable impact{exclusion_extra}"""


class CodeReviewFinding(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description=(
            "HIGH: bug that will cause incorrect behavior in production. "
            "MEDIUM: latent bug under specific conditions, or a clear maintainability issue. "
            "LOW: minor concerns worth surfacing but not blocking."
        ),
    )
    category: str = Field(examples=["logic_error"])
    source: str = Field(examples=["python_code_review"])
    description: str = Field(examples=["Off-by-one in loop bound."])
    recommendation: str = Field(examples=["Use < instead of <=."])
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "high: confident this is a real issue. "
            "medium: likely real but some ambiguity. "
            "low: speculative."
        ),
    )


class CodeReviewOutput(BaseModel):
    findings: list[CodeReviewFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}],
    )


class PythonCodeReview(ClaudeAgentNode):
    def __init__(
        self,
        *,
        scope: Literal["diff", "full_repo"] = "diff",
        base_ref: str = "main",
        **kwargs,
    ) -> None:
        kwargs.setdefault("model", OPUS_4_6)

        if scope == "diff":
            scope_section = (
                "Diff mode: only review changes between the base ref and\n"
                "`HEAD`. Ignore pre-existing issues outside the diff."
            )
            method_intro = (
                "Run the git diff command from the prompt and read every\nchanged file."
            )
            exclusion_extra = "\n- Pre-existing issues outside the diff"
            prompt = (
                f"Review only changes introduced by the diff against {base_ref}. "
                f"Start by running `git diff {base_ref}...HEAD` and reading the changed files."
            )
        else:
            scope_section = (
                "Full repo: review all Python source files in the\nrepository."
            )
            method_intro = (
                "List all Python source files with `git ls-files '*.py'`\n"
                "and read each one."
            )
            exclusion_extra = ""
            prompt = (
                "Review all Python source files in the repository. "
                "Start by running `git ls-files '*.py'` and reading each file."
            )

        super().__init__(
            name="python_code_review",
            system_prompt=_SKILL.format(
                scope_section=scope_section,
                method_intro=method_intro,
                exclusion_extra=exclusion_extra,
            ),
            output=CodeReviewOutput,
            prompt_template=prompt,
            allow=[
                "Read",
                "Glob",
                "Grep",
                "Bash(git diff*)",
                "Bash(git log*)",
                "Bash(git show*)",
                "Bash(git blame*)",
                "Bash(git status*)",
                "Bash(git ls-files*)",
            ],
            deny=[],
            on_unmatched="deny",
            **kwargs,
        )
```

The key changes: (1) removed the `## Output` and severity guide sections from `_SKILL`, (2) defined `CodeReviewFinding` and `CodeReviewOutput` Pydantic models, (3) passed `output=CodeReviewOutput` to `super().__init__()`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestCodeReviewModels tests/test_review_selfcontained.py -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add agentpipe/nodes/python_code_review.py tests/test_schema.py
git commit -m "feat: PythonCodeReview uses Pydantic output model"
```

---

### Task 7: Migrate `PythonSecurityAudit` to Pydantic output

**Files:**
- Modify: `agentpipe/nodes/python_security_audit.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_schema.py`:

```python
class TestSecurityAuditModels:
    def test_security_audit_output_validates(self):
        from agentpipe.nodes.python_security_audit import SecurityAuditOutput

        data = {
            "findings": [
                {
                    "file": "a.py",
                    "line": 10,
                    "severity": "HIGH",
                    "category": "command_injection",
                    "source": "python_security_audit",
                    "description": "User input in subprocess.",
                    "exploit_scenario": "Attacker injects shell commands.",
                    "recommendation": "Use list args.",
                    "confidence": "high",
                }
            ],
            "summary": {"files_reviewed": 5, "high": 1, "medium": 0, "low": 0},
        }
        output = SecurityAuditOutput.model_validate(data)
        assert len(output.findings) == 1
        assert output.findings[0].exploit_scenario == "Attacker injects shell commands."

    def test_security_audit_node_has_output_instructions(self):
        from agentpipe.nodes.python_security_audit import PythonSecurityAudit

        node = PythonSecurityAudit()
        assert "## Output" in node.system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestSecurityAuditModels -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Define Pydantic models and wire `output=`**

In `agentpipe/nodes/python_security_audit.py`: add `from pydantic import BaseModel, Field` import, define `SecurityAuditFinding` and `SecurityAuditOutput` models (same pattern as code review but with `exploit_scenario` field), remove the `## Output` and severity guide sections from `_SKILL`, and pass `output=SecurityAuditOutput` to `super().__init__()`.

`SecurityAuditFinding` fields:
```python
class SecurityAuditFinding(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description=(
            "HIGH: directly exploitable — RCE, auth bypass, data breach, account takeover. "
            "MEDIUM: exploitable under specific but realistic conditions. "
            "LOW: defense-in-depth or limited-impact issues."
        ),
    )
    category: str = Field(examples=["command_injection"])
    source: str = Field(examples=["python_security_audit"])
    description: str = Field(examples=["User input passed to subprocess with shell=True."])
    exploit_scenario: str = Field(examples=["Attacker injects shell commands via the name parameter."])
    recommendation: str = Field(examples=["Use subprocess.run() with a list argument instead of shell=True."])
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "high: confident this is exploitable. "
            "medium: likely exploitable but some ambiguity. "
            "low: speculative."
        ),
    )


class SecurityAuditOutput(BaseModel):
    findings: list[SecurityAuditFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"files_reviewed": 12, "high": 1, "medium": 0, "low": 0}],
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestSecurityAuditModels -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/nodes/python_security_audit.py tests/test_schema.py
git commit -m "feat: PythonSecurityAudit uses Pydantic output model"
```

---

### Task 8: Migrate `DocsReview` to Pydantic output

**Files:**
- Modify: `agentpipe/nodes/docs_review.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_schema.py`:

```python
class TestDocsReviewModels:
    def test_docs_review_output_validates(self):
        from agentpipe.nodes.docs_review import DocsReviewOutput

        data = {
            "findings": [
                {
                    "file": "README.md",
                    "line": 10,
                    "severity": "MEDIUM",
                    "category": "doc_drift",
                    "source": "docs_review",
                    "description": "README references removed function.",
                    "recommendation": "Update to new name.",
                    "confidence": "high",
                }
            ],
            "summary": {"files_reviewed": 5, "high": 0, "medium": 1, "low": 0},
        }
        output = DocsReviewOutput.model_validate(data)
        assert len(output.findings) == 1

    def test_docs_review_node_has_output_instructions(self):
        from agentpipe.nodes.docs_review import DocsReview

        node = DocsReview()
        assert "## Output" in node.system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestDocsReviewModels -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Define Pydantic models and wire `output=`**

Same pattern. `DocsReviewFinding` fields: `file`, `line`, `severity` (Literal with docs-specific descriptions: HIGH = actively misleading, MEDIUM = out of date, LOW = minor stale reference), `category`, `source`, `description`, `recommendation`, `confidence`. `DocsReviewOutput` has `findings: list[DocsReviewFinding]` and `summary: dict[str, int]`. Remove `## Output` and severity sections from `_SKILL`. Pass `output=DocsReviewOutput`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestDocsReviewModels -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/nodes/docs_review.py tests/test_schema.py
git commit -m "feat: DocsReview uses Pydantic output model"
```

---

### Task 9: Migrate `PythonTest` to Pydantic output

**Files:**
- Modify: `agentpipe/nodes/python_test.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_schema.py`:

```python
class TestPythonTestModels:
    def test_test_output_validates(self):
        from agentpipe.nodes.python_test import TestOutput

        data = {
            "findings": [
                {
                    "file": "tests/test_foo.py",
                    "line": 10,
                    "severity": "HIGH",
                    "category": "test_failure",
                    "source": "python_test",
                    "description": "Assertion failed.",
                    "recommendation": "Fix the bug.",
                    "confidence": "high",
                }
            ],
            "summary": {
                "tests_run": 50,
                "tests_passed": 49,
                "tests_failed": 1,
                "tests_skipped": 0,
                "tests_xfailed": 0,
                "high": 1,
                "medium": 0,
                "low": 0,
            },
        }
        output = TestOutput.model_validate(data)
        assert output.summary["tests_run"] == 50
        assert len(output.findings) == 1

    def test_test_node_has_output_instructions(self):
        from agentpipe.nodes.python_test import PythonTest

        node = PythonTest()
        assert "## Output" in node.system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestPythonTestModels -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Define Pydantic models and wire `output=`**

Same pattern. `TestFinding` fields: `file`, `line`, `severity` (HIGH: bug affecting production, MEDIUM: edge case regression, LOW: flaky test), `category`, `source`, `description`, `recommendation`, `confidence`. `TestOutput` has `findings: list[TestFinding]` and `summary: dict[str, int]` (with example showing tests_run, tests_passed, tests_failed, tests_skipped, tests_xfailed, high, medium, low). Remove `## Output` and severity sections from `_SKILL`. Pass `output=TestOutput`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestPythonTestModels -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/nodes/python_test.py tests/test_schema.py
git commit -m "feat: PythonTest uses Pydantic output model"
```

---

### Task 10: Migrate `PythonDependencyAudit` to Pydantic output

**Files:**
- Modify: `agentpipe/nodes/python_dependency_audit.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_schema.py`:

```python
class TestDependencyAuditModels:
    def test_dependency_audit_output_validates(self):
        from agentpipe.nodes.python_dependency_audit import DependencyAuditOutput

        data = {
            "findings": [
                {
                    "file": "pyproject.toml",
                    "line": 1,
                    "severity": "HIGH",
                    "category": "vulnerable_dependency",
                    "source": "python_dependency_audit",
                    "description": "requests 2.28.0 has CVE-2023-XXXXX.",
                    "recommendation": "Upgrade to requests>=2.31.0.",
                    "confidence": "high",
                }
            ],
            "summary": {"packages_scanned": 45, "high": 1, "medium": 0, "low": 0},
        }
        output = DependencyAuditOutput.model_validate(data)
        assert len(output.findings) == 1

    def test_dependency_audit_node_has_output_instructions(self):
        from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit

        node = PythonDependencyAudit()
        assert "## Output" in node.system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestDependencyAuditModels -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Define Pydantic models and wire `output=`**

`DependencyAuditFinding` fields: `file`, `line`, `severity` (HIGH: CVSS >= 7.0 or active exploitation, MEDIUM: CVSS 4.0-6.9, LOW: CVSS < 4.0), `category`, `source`, `description`, `recommendation`, `confidence`. `DependencyAuditOutput` has `findings` and `summary` (example: `{"packages_scanned": 45, "high": 1, "medium": 0, "low": 0}`). Remove `## Output` and severity sections from `_SKILL`. Pass `output=DependencyAuditOutput`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestDependencyAuditModels -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/nodes/python_dependency_audit.py tests/test_schema.py
git commit -m "feat: PythonDependencyAudit uses Pydantic output model"
```

---

### Task 11: Add `output=` to `PythonTypeCheck` ShellNode

**Files:**
- Modify: `agentpipe/nodes/python_type_check.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_schema.py`:

```python
class TestTypeCheckModels:
    def test_type_check_output_validates(self):
        from agentpipe.nodes.python_type_check import TypeCheckOutput

        data = {
            "findings": [
                {
                    "file": "foo.py",
                    "line": 10,
                    "severity": "HIGH",
                    "category": "type_error",
                    "source": "python_type_check",
                    "description": "Incompatible types.",
                    "confidence": "high",
                }
            ],
            "summary": {"high": 1, "medium": 0, "low": 0},
        }
        output = TypeCheckOutput.model_validate(data)
        assert len(output.findings) == 1

    def test_type_check_node_has_output_cls(self):
        from agentpipe.nodes.python_type_check import PythonTypeCheck, TypeCheckOutput

        node = PythonTypeCheck()
        assert node.output_cls is TypeCheckOutput
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestTypeCheckModels -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Define Pydantic models and wire `output=`**

In `agentpipe/nodes/python_type_check.py`, add Pydantic imports and define:

```python
from pydantic import BaseModel, Field


class TypeCheckFinding(BaseModel):
    file: str = Field(examples=["foo.py"])
    line: int = Field(examples=[10])
    severity: str = Field(examples=["HIGH"])
    category: str = Field(examples=["type_error"])
    source: str = Field(examples=["python_type_check"])
    description: str = Field(examples=["Incompatible types in assignment."])
    confidence: str = Field(examples=["high"])


class TypeCheckOutput(BaseModel):
    findings: list[TypeCheckFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"high": 0, "medium": 0, "low": 0}],
    )
```

Then pass `output=TypeCheckOutput` to `super().__init__()`:

```python
        super().__init__(
            name="python_type_check",
            command=[sys.executable, "-c", _MYPY_SCRIPT],
            output=TypeCheckOutput,
            check=False,
            timeout=timeout,
            verbosity=verbosity,
        )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_schema.py::TestTypeCheckModels -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/nodes/python_type_check.py tests/test_schema.py
git commit -m "feat: PythonTypeCheck uses Pydantic output model"
```

---

### Task 12: Migrate `ResolveFindings` to Pydantic-based extraction

**Files:**
- Modify: `agentpipe/nodes/resolve_findings.py`
- Modify: `tests/test_resolve_findings.py`

- [ ] **Step 1: Write failing tests for the new behavior**

Replace `tests/test_resolve_findings.py` entirely:

```python
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field

from agentpipe.nodes.resolve_findings import (
    ResolveFindings,
    ResolveOutput,
    _extract_items_from_state,
    _format_findings,
    _select_by_input,
)


class FakeUpstreamFinding(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    source: str = ""
    description: str = ""


class FakeUpstreamOutput(BaseModel):
    findings: list[FakeUpstreamFinding] = Field(default_factory=list)


class TestExtractItemsFromState:
    def test_extracts_from_pydantic_model(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="HIGH",
                    category="logic_error", description="bug",
                ),
            ]
        )
        items = _extract_items_from_state(["code_review"], {"code_review": upstream})
        assert len(items) == 1
        assert items[0]["file"] == "a.py"
        assert items[0]["source"] == "code_review"

    def test_sorts_by_severity(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="LOW",
                    category="clarity", description="minor",
                ),
                FakeUpstreamFinding(
                    file="b.py", line=2, severity="CRITICAL",
                    category="logic_error", description="critical",
                ),
            ]
        )
        items = _extract_items_from_state(["review"], {"review": upstream})
        assert items[0]["severity"] == "CRITICAL"
        assert items[1]["severity"] == "LOW"

    def test_multiple_upstream_models(self):
        review = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="HIGH",
                    category="logic_error", description="bug",
                ),
            ]
        )
        security = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="b.py", line=2, severity="MEDIUM",
                    category="injection", description="sql inj",
                ),
            ]
        )
        items = _extract_items_from_state(
            ["code_review", "security_audit"],
            {"code_review": review, "security_audit": security},
        )
        assert len(items) == 2
        assert items[0]["severity"] == "HIGH"
        assert items[0]["source"] == "code_review"

    def test_skips_none_upstream(self):
        items = _extract_items_from_state(["missing"], {"missing": None})
        assert items == []

    def test_empty_findings_returns_empty(self):
        upstream = FakeUpstreamOutput(findings=[])
        items = _extract_items_from_state(["review"], {"review": upstream})
        assert items == []


class TestFormatFindings:
    def test_no_findings(self):
        result = _format_findings([])
        assert "No findings" in result

    def test_formats_numbered_list(self):
        findings = [
            {
                "severity": "HIGH",
                "source": "code_review",
                "file": "a.py",
                "line": 10,
                "category": "logic_error",
                "description": "Off-by-one error",
            },
            {
                "severity": "LOW",
                "source": "docs_review",
                "file": "b.py",
                "line": 5,
                "category": "docstring_drift",
                "description": "Stale docstring",
            },
        ]
        result = _format_findings(findings)
        assert "1" in result
        assert "2" in result
        assert "HIGH" in result
        assert "LOW" in result
        assert "a.py:10" in result


class TestSelectByInput:
    def _findings(self):
        return [
            {"severity": "CRITICAL", "description": "a"},
            {"severity": "HIGH", "description": "b"},
            {"severity": "MEDIUM", "description": "c"},
            {"severity": "LOW", "description": "d"},
        ]

    def test_all(self):
        assert len(_select_by_input(self._findings(), "all")) == 4

    def test_high_plus(self):
        selected = _select_by_input(self._findings(), "high")
        assert all(f["severity"] in ("CRITICAL", "HIGH") for f in selected)
        assert len(selected) == 2

    def test_medium_plus(self):
        selected = _select_by_input(self._findings(), "medium+")
        assert len(selected) == 3

    def test_by_numbers(self):
        selected = _select_by_input(self._findings(), "1, 3")
        assert len(selected) == 2
        assert selected[0]["description"] == "a"
        assert selected[1]["description"] == "c"

    def test_invalid_input_returns_empty(self):
        assert _select_by_input(self._findings(), "gibberish") == []


class TestResolveOutput:
    def test_resolve_output_validates(self):
        data = {
            "fixed": [
                {
                    "file": "a.py",
                    "line": 42,
                    "category": "logic_error",
                    "source": "python_code_review",
                    "description": "Fixed off-by-one.",
                }
            ],
            "skipped": [],
        }
        output = ResolveOutput.model_validate(data)
        assert len(output.fixed) == 1


class TestResolveFindingsNode:
    def test_constructs_with_defaults(self):
        node = ResolveFindings()
        assert callable(node)
        assert node.name == "resolve_findings"

    def test_no_findings_returns_immediately(self):
        upstream = FakeUpstreamOutput(findings=[])
        node = ResolveFindings(reads_from=["code_review"])
        result = asyncio.run(
            node({"working_dir": "/tmp", "code_review": upstream})
        )
        assert result["last_cost_usd"] == 0.0
        assert isinstance(result["resolve_findings"], ResolveOutput)
        assert result["resolve_findings"].fixed == []

    def test_auto_mode_skips_low_severity(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="LOW",
                    category="clarity", description="minor",
                ),
            ]
        )
        node = ResolveFindings(reads_from=["review"], interactive=False)
        result = asyncio.run(
            node({"working_dir": "/tmp", "review": upstream})
        )
        assert result["last_cost_usd"] == 0.0

    def test_interactive_none_skips(self):
        upstream = FakeUpstreamOutput(
            findings=[
                FakeUpstreamFinding(
                    file="a.py", line=1, severity="HIGH",
                    category="logic_error", description="bug",
                ),
            ]
        )

        async def ask_none(_summary):
            return "none"

        node = ResolveFindings(
            reads_from=["review"],
            interactive=True,
            ask_findings=ask_none,
        )
        result = asyncio.run(
            node({"working_dir": "/tmp", "review": upstream})
        )
        assert result["last_cost_usd"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_resolve_findings.py -x -q --no-header`
Expected: FAIL — `ImportError: cannot import name '_extract_items_from_state'`

- [ ] **Step 3: Rewrite `resolve_findings.py`**

Replace `agentpipe/nodes/resolve_findings.py` with the updated version that:

1. Defines `FixedItem`, `SkippedItem`, `ResolveOutput` Pydantic models
2. Replaces `_extract_findings` with `_extract_items_from_state` (walks Pydantic model fields for lists)
3. Uses `_extract_items_from_state` in `__call__` instead of `_extract_findings(prior)`
4. Returns `ResolveOutput` instances instead of JSON strings
5. Passes `output=ResolveOutput` to the inner fixer's `ClaudeAgentNode`
6. Removes the hand-written `## Output` section from `_SKILL`
7. Updates `_build_prior_results` to call `model_dump_json()` on upstream state

Key implementation details:

```python
from pydantic import BaseModel, Field


class FixedItem(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[42])
    category: str = Field(examples=["logic_error"])
    source: str = Field(examples=["python_code_review"])
    description: str = Field(examples=["What was fixed, one sentence."])


class SkippedItem(BaseModel):
    file: str = Field(examples=["path/to/file.py"])
    line: int = Field(examples=[10])
    category: str = Field(examples=["clarity"])
    source: str = Field(examples=["python_code_review"])
    reason: str = Field(examples=["False positive — the code is correct because..."])


class ResolveOutput(BaseModel):
    fixed: list[FixedItem] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
```

The `_extract_items_from_state` function:

```python
def _extract_items_from_state(
    reads_from_keys: list[str], state: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in reads_from_keys:
        upstream = state.get(key)
        if upstream is None:
            continue
        data = upstream.model_dump()
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                for item in value:
                    item.setdefault("source", key)
                    items.append(item)
    items.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "LOW"), 99))
    return items
```

The `_build_prior_results` method:

```python
    def _build_prior_results(self, state: dict[str, Any]) -> str:
        parts = ["## Prior results\n"]
        for key in self._reads_from_keys:
            upstream = state.get(key)
            if upstream is None:
                continue
            serialized = upstream.model_dump_json(indent=2)
            parts.append(f"### {key}\n```json\n{serialized}\n```\n")
        return "\n".join(parts) if len(parts) > 1 else ""
```

The `__call__` changes: use `_extract_items_from_state(self._reads_from_keys, state)` instead of `_extract_findings(prior)`. Return `ResolveOutput` instances instead of JSON strings. The inner fixer agent now uses `output=ResolveOutput`. When no findings or user skips, return `ResolveOutput(fixed=[], skipped=...)` directly.

Remove `_SKILL`'s `## Output` section — it gets generated from `ResolveOutput` via `output=`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_resolve_findings.py -x -q --no-header`
Expected: all tests PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass (some existing tests may need imports updated — fix if needed)

- [ ] **Step 6: Commit**

```bash
git add agentpipe/nodes/resolve_findings.py tests/test_resolve_findings.py
git commit -m "feat: ResolveFindings uses Pydantic models, removes regex parsing"
```

---

### Task 13: Update `display.py` to use `model_dump()`

**Files:**
- Modify: `agentpipe/display.py:167-228`
- Modify: `tests/test_display.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_display.py`:

```python
class TestPrintResultsWithPydantic:
    def test_print_results_with_resolve_output(self, capsys):
        from agentpipe.nodes.resolve_findings import ResolveOutput, FixedItem

        d = Display(steps=["a"], title="T", live=False)
        resolve = ResolveOutput(
            fixed=[
                FixedItem(
                    file="a.py",
                    line=42,
                    category="logic_error",
                    source="review",
                    description="Fixed off-by-one.",
                )
            ],
            skipped=[],
        )
        d.print_results({"a": 0.05}, node_outputs={"resolve_findings": resolve})
        out = capsys.readouterr().out
        assert "a.py" in out
        assert "Fixed" in out
```

- [ ] **Step 2: Run tests to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_display.py::TestPrintResultsWithPydantic -x -q --no-header`
Expected: FAIL (current code calls `json.loads()` on a Pydantic model)

- [ ] **Step 3: Update `print_results` in `display.py`**

Replace the `print_results` method's resolve_findings handling block (lines ~187-227) with:

```python
        if node_outputs:
            resolve_output = node_outputs.get("resolve_findings")
            if resolve_output is not None:
                self._stdout_console.print()
                self._stdout_console.print(
                    Text("Resolve findings", style="bold underline")
                )
                data = resolve_output.model_dump()
                fixed = data.get("fixed", [])
                skipped = data.get("skipped", [])
                if fixed:
                    self._stdout_console.print(
                        Text(f"\n  Fixed ({len(fixed)}):", style="bold green")
                    )
                    for f in fixed:
                        file = f.get("file", "?")
                        line = f.get("line", "?")
                        desc = f.get("description", "")
                        self._stdout_console.print(
                            f"    {file}:{line} — {desc}", highlight=False
                        )
                if skipped:
                    self._stdout_console.print(
                        Text(f"\n  Skipped ({len(skipped)}):", style="bold yellow")
                    )
                    for s in skipped:
                        file = s.get("file", "?")
                        line = s.get("line", "?")
                        reason = s.get("reason", "")
                        self._stdout_console.print(
                            f"    {file}:{line} — {reason}", highlight=False
                        )
                if not fixed and not skipped:
                    self._stdout_console.print(
                        "  No findings to resolve.", highlight=False
                    )
```

Also remove the `import json` that was inside the method and the `except (json.JSONDecodeError, TypeError)` fallback.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_display.py -x -q --no-header`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agentpipe/display.py tests/test_display.py
git commit -m "feat: display.print_results uses model_dump() instead of json.loads()"
```

---

### Task 14: Update `agentpipe/nodes/__init__.py` exports

**Files:**
- Modify: `agentpipe/nodes/__init__.py`

- [ ] **Step 1: Replace `agentpipe/nodes/__init__.py`**

```python
from agentpipe.nodes.base import ClaudeAgentNode, ShellNode
from agentpipe.nodes.docs_review import DocsReview
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit
from agentpipe.nodes.python_ensure_tools import PythonEnsureTools
from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_test import PythonTest
from agentpipe.nodes.python_type_check import PythonTypeCheck
from agentpipe.nodes.resolve_findings import ResolveFindings

__all__ = [
    "ClaudeAgentNode",
    "ShellNode",
    "DocsReview",
    "PythonCodeReview",
    "PythonDependencyAudit",
    "PythonEnsureTools",
    "PythonFormat",
    "PythonLint",
    "PythonSecurityAudit",
    "PythonTest",
    "PythonTypeCheck",
    "ResolveFindings",
]
```

- [ ] **Step 2: Verify imports work**

Run: `.venv/bin/python -c "from agentpipe.nodes import PythonCodeReview, PythonLint, ResolveFindings; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add agentpipe/nodes/__init__.py
git commit -m "feat: export all node classes from agentpipe.nodes"
```

---

### Task 15: Update `agentpipe/__init__.py` exports

**Files:**
- Modify: `agentpipe/__init__.py`

- [ ] **Step 1: Replace `agentpipe/__init__.py`**

Remove all `_old` imports. Add new node class imports:

```python
"""agentpipe: deterministic AI pipelines powered by the Claude Agent SDK."""

from agentpipe.display import Display
from agentpipe.models import (
    HAIKU_4_5,
    OPUS_4_6,
    OPUS_4_7,
    SONNET_4_6,
    detect_provider,
    resolve_model,
)
from agentpipe.nodes.base import ClaudeAgentNode, ShellNode, Verbosity
from agentpipe.nodes.docs_review import DocsReview
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit
from agentpipe.nodes.python_ensure_tools import PythonEnsureTools
from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_test import PythonTest
from agentpipe.nodes.python_type_check import PythonTypeCheck
from agentpipe.nodes.resolve_findings import ResolveFindings
from agentpipe.permissions import PermissionRule, ask_via_stdin
from agentpipe.pipeline import Pipeline
from agentpipe.validation import OutputKeyConflict, validate_node_outputs
from agentpipe.skills import (
    JAVASCRIPT_CLEAN_CODE,
    JAVASCRIPT_SECURITY,
    PYTHON_CLEAN_CODE,
    PYTHON_SECURITY,
    RUST_CLEAN_CODE,
    RUST_SECURITY,
)

__all__ = [
    # Core
    "Pipeline",
    "Display",
    "ClaudeAgentNode",
    "ShellNode",
    "Verbosity",
    # Models
    "HAIKU_4_5",
    "OPUS_4_6",
    "OPUS_4_7",
    "SONNET_4_6",
    "detect_provider",
    "resolve_model",
    # Permissions
    "PermissionRule",
    "ask_via_stdin",
    # Node classes
    "DocsReview",
    "PythonCodeReview",
    "PythonDependencyAudit",
    "PythonEnsureTools",
    "PythonFormat",
    "PythonLint",
    "PythonSecurityAudit",
    "PythonTest",
    "PythonTypeCheck",
    "ResolveFindings",
    # Validation
    "OutputKeyConflict",
    "validate_node_outputs",
    # Skills
    "JAVASCRIPT_CLEAN_CODE",
    "JAVASCRIPT_SECURITY",
    "PYTHON_CLEAN_CODE",
    "PYTHON_SECURITY",
    "RUST_CLEAN_CODE",
    "RUST_SECURITY",
]

__version__ = "0.1.0"
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests pass. If any test imports `_old` factories, update them.

- [ ] **Step 3: Commit**

```bash
git add agentpipe/__init__.py
git commit -m "feat: clean up top-level exports, remove _old references"
```

---

### Task 16: Fix remaining tests that reference old APIs

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: any other test files that import from `_old`

- [ ] **Step 1: Identify tests importing `_old`**

Run: `grep -rn "_old" tests/`
Expected: shows files importing old factory functions

- [ ] **Step 2: Update `tests/test_pipeline.py`**

Replace `_old` imports with new class-based nodes:

```python
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_format import PythonFormat
```

Replace `python_lint_node()` calls with `PythonLint()`, and `python_format_node()` calls with `PythonFormat()`.

- [ ] **Step 3: Update any other test files that import from `_old`**

For each file found in step 1, replace the `_old` factory imports with the corresponding new class instantiations.

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: migrate all tests from _old factories to new node classes"
```

---

### Task 17: Delete `agentpipe/nodes/_old/` directory

**Files:**
- Delete: `agentpipe/nodes/_old/` (entire directory)

- [ ] **Step 1: Verify no remaining references**

Run: `grep -rn "_old" agentpipe/ tests/`
Expected: no hits (or only in `_old/` itself)

- [ ] **Step 2: Delete the directory**

```bash
git rm -r agentpipe/nodes/_old/
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete agentpipe/nodes/_old/ compatibility layer"
```

---

### Task 18: Final integration test — full test suite

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all tests PASS

- [ ] **Step 2: Run import smoke test**

Run:
```bash
.venv/bin/python -c "
from agentpipe.nodes import (
    PythonCodeReview, PythonSecurityAudit, DocsReview,
    PythonTest, PythonDependencyAudit, PythonTypeCheck,
    PythonLint, PythonFormat, PythonEnsureTools,
    ResolveFindings,
)
from agentpipe.schema import generate_output_instructions, parse_output
from agentpipe.nodes.python_code_review import CodeReviewOutput
from agentpipe.nodes.resolve_findings import ResolveOutput

node = PythonCodeReview()
assert '## Output' in node.system_prompt
assert node.output_cls is CodeReviewOutput

print('All imports and wiring OK')
"
```
Expected: prints `All imports and wiring OK`

- [ ] **Step 3: Commit any remaining fixes**

If any tests needed fixing, commit them here.
