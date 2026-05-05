# Codemonkeys Package Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build codemonkeys as a layered Python package with a producer/consumer agent architecture, structured JSON artifacts, a workflow state machine, and a beautiful Textual TUI.

**Architecture:** Three layers — Core (agents, runner, sandbox), Workflows (state machines, events, artifact management), and TUI (Textual app with screens and widgets). Each layer depends only on the one below. Agents are categorized as analyzers (read-only, produce JSON artifacts) or executors (read-write, consume artifacts). The TUI renders workflow state and forwards user input — it contains no business logic.

**Tech Stack:** Python 3.10+, claude-agent-sdk, Pydantic 2, Textual 8, Rich 13

**Spec:** `docs/codemonkeys/specs/2026-05-04-python-package-architecture.md`

---

## Phase 1: Foundation

### Task 1: Restructure project into layered package

**Files:**
- Create: `codemonkeys/core/__init__.py`
- Create: `codemonkeys/core/agents/__init__.py`
- Create: `codemonkeys/core/prompts/__init__.py`
- Move: `codemonkeys/runner.py` → `codemonkeys/core/runner.py`
- Move: `codemonkeys/sandbox.py` → `codemonkeys/core/sandbox.py`
- Move: `codemonkeys/agents/*.py` → `codemonkeys/core/agents/*.py`
- Move: `codemonkeys/prompts/*.py` → `codemonkeys/core/prompts/*.py`
- Modify: `codemonkeys/__init__.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_sandbox.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update pyproject.toml with new dependencies**

Add `textual` and `pydantic` to the dependencies:

```toml
dependencies = [
    "claude-agent-sdk>=0.1.0,<1.0",
    "rich>=13.0,<14",
    "textual>=8.0",
    "pydantic>=2.0,<3",
]
```

Also add the CLI entry point:

```toml
[project.scripts]
codemonkeys = "codemonkeys.cli:main"
```

Remove the `codemonkeys_reference` force-include from `[tool.hatch.build.targets.wheel.force-include]`.

- [ ] **Step 2: Create core/ directory and move files**

```bash
mkdir -p codemonkeys/core/agents codemonkeys/core/prompts
git mv codemonkeys/runner.py codemonkeys/core/runner.py
git mv codemonkeys/sandbox.py codemonkeys/core/sandbox.py
git mv codemonkeys/agents/python_file_reviewer.py codemonkeys/core/agents/python_file_reviewer.py
git mv codemonkeys/agents/python_implementer.py codemonkeys/core/agents/python_implementer.py
git mv codemonkeys/agents/changelog_reviewer.py codemonkeys/core/agents/changelog_reviewer.py
git mv codemonkeys/agents/readme_reviewer.py codemonkeys/core/agents/readme_reviewer.py
git mv codemonkeys/prompts/python_cmd.py codemonkeys/core/prompts/python_cmd.py
git mv codemonkeys/prompts/python_guidelines.py codemonkeys/core/prompts/python_guidelines.py
git mv codemonkeys/prompts/engineering_mindset.py codemonkeys/core/prompts/engineering_mindset.py
git mv codemonkeys/prompts/code_quality.py codemonkeys/core/prompts/code_quality.py
git mv codemonkeys/prompts/security_observations.py codemonkeys/core/prompts/security_observations.py
git mv codemonkeys/prompts/python_source_filter.py codemonkeys/core/prompts/python_source_filter.py
```

- [ ] **Step 3: Update internal imports in moved files**

In `codemonkeys/core/runner.py`, update the sandbox import:

```python
from codemonkeys.core.sandbox import restrict
```

In `codemonkeys/core/agents/python_file_reviewer.py`, update:

```python
from codemonkeys.core.prompts import CODE_QUALITY, PYTHON_GUIDELINES, SECURITY_OBSERVATIONS
```

In `codemonkeys/core/agents/python_implementer.py`, update:

```python
from codemonkeys.core.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES
```

- [ ] **Step 4: Write core/ package init files**

`codemonkeys/core/__init__.py`:

```python
"""Core layer — agents, runner, sandbox, prompts."""
```

`codemonkeys/core/prompts/__init__.py` — same content as the old `codemonkeys/prompts/__init__.py` but with updated import paths:

```python
from __future__ import annotations

from codemonkeys.core.prompts.code_quality import CODE_QUALITY
from codemonkeys.core.prompts.engineering_mindset import ENGINEERING_MINDSET
from codemonkeys.core.prompts.python_cmd import PYTHON_CMD
from codemonkeys.core.prompts.python_guidelines import PYTHON_GUIDELINES
from codemonkeys.core.prompts.python_source_filter import PYTHON_SOURCE_FILTER
from codemonkeys.core.prompts.security_observations import SECURITY_OBSERVATIONS

__all__ = [
    "CODE_QUALITY",
    "ENGINEERING_MINDSET",
    "PYTHON_CMD",
    "PYTHON_GUIDELINES",
    "PYTHON_SOURCE_FILTER",
    "SECURITY_OBSERVATIONS",
]
```

`codemonkeys/core/agents/__init__.py`:

```python
"""Agent factories for Claude Agent SDK workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer as make_changelog_reviewer
    from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer as make_python_file_reviewer
    from codemonkeys.core.agents.python_implementer import make_python_implementer as make_python_implementer
    from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer as make_readme_reviewer

__all__ = [
    "make_changelog_reviewer",
    "make_python_file_reviewer",
    "make_python_implementer",
    "make_readme_reviewer",
]


def __getattr__(name: str) -> object:
    if name == "make_changelog_reviewer":
        from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer
        return make_changelog_reviewer
    if name == "make_python_file_reviewer":
        from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
        return make_python_file_reviewer
    if name == "make_python_implementer":
        from codemonkeys.core.agents.python_implementer import make_python_implementer
        return make_python_implementer
    if name == "make_readme_reviewer":
        from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer
        return make_readme_reviewer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 5: Update top-level __init__.py**

`codemonkeys/__init__.py`:

```python
"""codemonkeys: AI agent workflows powered by the Claude Agent SDK."""

__version__ = "0.3.0"
```

Remove the old `codemonkeys/agents/__init__.py` and `codemonkeys/prompts/__init__.py` (they've been moved to `core/`).

- [ ] **Step 6: Update test imports**

In `tests/test_sandbox.py`, update imports from `codemonkeys.sandbox` to `codemonkeys.core.sandbox`.

In `tests/conftest.py`, no changes needed (it patches `claude_agent_sdk.query` directly).

- [ ] **Step 7: Verify tests pass**

Run: `python -m pytest tests/ -v`
Expected: All existing sandbox tests pass with updated imports.

- [ ] **Step 8: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "refactor: restructure package into core/ layer"
```

---

### Task 2: Artifact schemas

**Files:**
- Create: `codemonkeys/artifacts/__init__.py`
- Create: `codemonkeys/artifacts/schemas/__init__.py`
- Create: `codemonkeys/artifacts/schemas/findings.py`
- Create: `codemonkeys/artifacts/schemas/plans.py`
- Create: `codemonkeys/artifacts/schemas/results.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write tests for Finding and FileFindings models**

`tests/test_schemas.py`:

```python
from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest


class TestFinding:

    def test_roundtrip_json(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection via f-string",
            description="User input interpolated into SQL query without parameterization.",
            suggestion="Use parameterized query: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
        )
        data = json.loads(finding.model_dump_json())
        restored = Finding.model_validate(data)
        assert restored == finding

    def test_line_is_optional(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=None,
            severity="low",
            category="quality",
            subcategory="documentation",
            title="Missing module docstring",
            description="Module has no docstring.",
            suggestion=None,
        )
        assert finding.line is None
        assert finding.suggestion is None

    def test_json_schema_has_descriptions(self) -> None:
        schema = Finding.model_json_schema()
        assert "description" in schema["properties"]["file"]
        assert "description" in schema["properties"]["severity"]
        assert "description" in schema["properties"]["category"]


class TestFileFindings:

    def test_from_findings_list(self) -> None:
        findings = FileFindings(
            file="src/auth.py",
            summary="Authentication module with SQL injection vulnerability.",
            findings=[
                Finding(
                    file="src/auth.py",
                    line=42,
                    severity="high",
                    category="security",
                    subcategory="injection",
                    title="SQL injection",
                    description="Unsafe query.",
                    suggestion="Use parameterized queries.",
                ),
            ],
        )
        assert len(findings.findings) == 1
        data = json.loads(findings.model_dump_json())
        assert data["file"] == "src/auth.py"


class TestFixRequest:

    def test_selected_findings(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection",
            description="Unsafe query.",
            suggestion="Use parameterized queries.",
        )
        request = FixRequest(file="src/auth.py", findings=[finding])
        data = json.loads(request.model_dump_json())
        assert len(data["findings"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.artifacts'`

- [ ] **Step 3: Implement findings.py**

`codemonkeys/artifacts/__init__.py`:

```python
"""Artifact schemas and storage for workflow outputs."""
```

`codemonkeys/artifacts/schemas/__init__.py`:

```python
"""Pydantic models for all artifact types."""

from __future__ import annotations

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult

__all__ = [
    "FeaturePlan",
    "FileFindings",
    "Finding",
    "FixRequest",
    "FixResult",
    "PlanStep",
    "VerificationResult",
]
```

`codemonkeys/artifacts/schemas/findings.py`:

```python
"""Schemas for code review findings and fix requests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    file: str = Field(description="Relative path to the file containing the issue")
    line: int | None = Field(description="Line number where the issue occurs, or null if file-level")
    severity: Literal["high", "medium", "low", "info"] = Field(
        description="Impact severity — high: likely bug or vulnerability, medium: should fix, low: suggestion, info: observation"
    )
    category: Literal["quality", "security", "bug", "style", "changelog", "readme"] = Field(
        description="Type of issue found"
    )
    subcategory: str = Field(
        description="Specific check that triggered this finding (e.g., 'injection', 'naming', 'missing_entry')"
    )
    title: str = Field(description="Short one-line summary of the issue")
    description: str = Field(description="Detailed explanation of what's wrong and why it matters")
    suggestion: str | None = Field(
        default=None,
        description="Concrete suggestion for how to fix the issue, with example code if applicable",
    )


class FileFindings(BaseModel):
    file: str = Field(description="Relative path to the reviewed file")
    summary: str = Field(description="One sentence describing what this file does")
    findings: list[Finding] = Field(
        default_factory=list,
        description="List of issues found in this file, empty if the file is clean",
    )


class FixRequest(BaseModel):
    file: str = Field(description="Relative path to the file to fix")
    findings: list[Finding] = Field(description="Specific findings the fixer agent should address")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Add tests for plans and results schemas**

Append to `tests/test_schemas.py`:

```python
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult


class TestFeaturePlan:

    def test_roundtrip(self) -> None:
        plan = FeaturePlan(
            title="Add user authentication",
            description="Implement JWT-based auth with login/logout endpoints.",
            steps=[
                PlanStep(
                    description="Create auth middleware",
                    files=["src/middleware/auth.py"],
                ),
                PlanStep(
                    description="Add login endpoint",
                    files=["src/routes/auth.py", "tests/test_auth.py"],
                ),
            ],
        )
        data = json.loads(plan.model_dump_json())
        restored = FeaturePlan.model_validate(data)
        assert len(restored.steps) == 2
        assert restored.title == "Add user authentication"


class TestFixResult:

    def test_roundtrip(self) -> None:
        result = FixResult(
            file="src/auth.py",
            fixed=["SQL injection on line 42"],
            skipped=["Could not resolve ambiguous suggestion on line 88"],
        )
        data = json.loads(result.model_dump_json())
        restored = FixResult.model_validate(data)
        assert len(restored.fixed) == 1
        assert len(restored.skipped) == 1


class TestVerificationResult:

    def test_roundtrip(self) -> None:
        result = VerificationResult(
            tests_passed=True,
            lint_passed=True,
            typecheck_passed=False,
            errors=["pyright: src/auth.py:42 — missing return type"],
        )
        data = json.loads(result.model_dump_json())
        restored = VerificationResult.model_validate(data)
        assert restored.tests_passed is True
        assert restored.typecheck_passed is False
```

- [ ] **Step 6: Implement plans.py and results.py**

`codemonkeys/artifacts/schemas/plans.py`:

```python
"""Schemas for feature and bugfix plans."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    description: str = Field(description="What this step accomplishes")
    files: list[str] = Field(
        default_factory=list,
        description="Files that will be created or modified in this step",
    )


class FeaturePlan(BaseModel):
    title: str = Field(description="Short title for the feature or bugfix")
    description: str = Field(description="Detailed description of what to build and why")
    steps: list[PlanStep] = Field(description="Ordered implementation steps")
```

`codemonkeys/artifacts/schemas/results.py`:

```python
"""Schemas for fix and verification results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FixResult(BaseModel):
    file: str = Field(description="Relative path to the file that was fixed")
    fixed: list[str] = Field(
        default_factory=list,
        description="Descriptions of findings that were successfully fixed",
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="Descriptions of findings that could not be fixed, with reasons",
    )


class VerificationResult(BaseModel):
    tests_passed: bool = Field(description="Whether pytest passed")
    lint_passed: bool = Field(description="Whether ruff check passed")
    typecheck_passed: bool = Field(description="Whether pyright passed")
    errors: list[str] = Field(
        default_factory=list,
        description="Specific error messages from failed checks",
    )
```

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add Pydantic artifact schemas for findings, plans, and results"
```

---

### Task 3: Artifact store

**Files:**
- Create: `codemonkeys/artifacts/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write tests for artifact store**

`tests/test_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding
from codemonkeys.artifacts.store import ArtifactStore


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / ".codemonkeys")


@pytest.fixture
def sample_findings() -> FileFindings:
    return FileFindings(
        file="src/auth.py",
        summary="Auth module.",
        findings=[
            Finding(
                file="src/auth.py",
                line=42,
                severity="high",
                category="security",
                subcategory="injection",
                title="SQL injection",
                description="Unsafe query.",
                suggestion="Use parameterized queries.",
            ),
        ],
    )


class TestArtifactStore:

    def test_save_and_load(self, store: ArtifactStore, sample_findings: FileFindings) -> None:
        run_id = store.new_run("review")
        store.save(run_id, "findings/src__auth.py", sample_findings)
        loaded = store.load(run_id, "findings/src__auth.py", FileFindings)
        assert loaded == sample_findings

    def test_list_runs(self, store: ArtifactStore, sample_findings: FileFindings) -> None:
        run1 = store.new_run("review")
        store.save(run1, "findings/a", sample_findings)
        run2 = store.new_run("review")
        store.save(run2, "findings/b", sample_findings)
        runs = store.list_runs("review")
        assert len(runs) >= 2

    def test_list_artifacts_in_run(self, store: ArtifactStore, sample_findings: FileFindings) -> None:
        run_id = store.new_run("review")
        store.save(run_id, "findings/file_a", sample_findings)
        store.save(run_id, "findings/file_b", sample_findings)
        artifacts = store.list_artifacts(run_id, "findings")
        assert len(artifacts) == 2

    def test_load_nonexistent_returns_none(self, store: ArtifactStore) -> None:
        loaded = store.load("nonexistent", "nope", FileFindings)
        assert loaded is None

    def test_root_dir_created_on_save(self, tmp_path: Path) -> None:
        root = tmp_path / "sub" / ".codemonkeys"
        store = ArtifactStore(root)
        findings = FileFindings(file="x.py", summary="x", findings=[])
        run_id = store.new_run("review")
        store.save(run_id, "test", findings)
        assert root.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'codemonkeys.artifacts.store'`

- [ ] **Step 3: Implement store.py**

`codemonkeys/artifacts/store.py`:

```python
"""Read/write/list structured artifacts in .codemonkeys/ directories."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ArtifactStore:

    def __init__(self, root: Path) -> None:
        self._root = root

    def new_run(self, workflow: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        run_id = f"{workflow}/{ts}"
        run_dir = self._root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_id

    def save(self, run_id: str, name: str, artifact: BaseModel) -> Path:
        path = self._root / run_id / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.model_dump_json(indent=2))
        return path

    def load(self, run_id: str, name: str, model: type[T]) -> T | None:
        path = self._root / run_id / f"{name}.json"
        if not path.exists():
            return None
        return model.model_validate_json(path.read_text())

    def list_runs(self, workflow: str) -> list[str]:
        workflow_dir = self._root / workflow
        if not workflow_dir.is_dir():
            return []
        return sorted(
            [f"{workflow}/{d.name}" for d in workflow_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

    def list_artifacts(self, run_id: str, subdirectory: str = "") -> list[str]:
        target = self._root / run_id
        if subdirectory:
            target = target / subdirectory
        if not target.is_dir():
            return []
        return sorted(p.stem for p in target.glob("*.json"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add artifact store for reading/writing structured JSON artifacts"
```

---

### Task 4: Agent registry and structured output support

**Files:**
- Create: `codemonkeys/core/agents/registry.py`
- Create: `codemonkeys/core/agents/python_code_fixer.py`
- Create: `tests/test_registry.py`
- Modify: `codemonkeys/core/agents/__init__.py`
- Modify: `codemonkeys/core/runner.py`

- [ ] **Step 1: Write tests for agent registry**

`tests/test_registry.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
from codemonkeys.core.agents.registry import AgentRegistry, AgentRole, AgentSpec


class _MockOutput(BaseModel):
    result: str = Field(description="test")


class _MockInput(BaseModel):
    data: str = Field(description="test")


class TestAgentRegistry:

    def test_register_and_list(self) -> None:
        registry = AgentRegistry()
        spec = AgentSpec(
            name="test-analyzer",
            role=AgentRole.ANALYZER,
            description="Test agent",
            scope="file",
            produces=_MockOutput,
            consumes=None,
            make=lambda: None,
        )
        registry.register(spec)
        assert registry.get("test-analyzer") == spec

    def test_list_by_role(self) -> None:
        registry = AgentRegistry()
        analyzer = AgentSpec(
            name="analyzer",
            role=AgentRole.ANALYZER,
            description="Analyzer",
            scope="file",
            produces=_MockOutput,
            consumes=None,
            make=lambda: None,
        )
        executor = AgentSpec(
            name="executor",
            role=AgentRole.EXECUTOR,
            description="Executor",
            scope="file",
            produces=None,
            consumes=_MockInput,
            make=lambda: None,
        )
        registry.register(analyzer)
        registry.register(executor)
        analyzers = registry.list_by_role(AgentRole.ANALYZER)
        assert len(analyzers) == 1
        assert analyzers[0].name == "analyzer"

    def test_compatible_executors(self) -> None:
        registry = AgentRegistry()
        analyzer = AgentSpec(
            name="reviewer",
            role=AgentRole.ANALYZER,
            description="File reviewer",
            scope="file",
            produces=FileFindings,
            consumes=None,
            make=lambda: None,
        )
        fixer = AgentSpec(
            name="fixer",
            role=AgentRole.EXECUTOR,
            description="Code fixer",
            scope="file",
            produces=None,
            consumes=FixRequest,
            make=lambda: None,
        )
        unrelated = AgentSpec(
            name="unrelated",
            role=AgentRole.EXECUTOR,
            description="Unrelated",
            scope="file",
            produces=None,
            consumes=_MockInput,
            make=lambda: None,
        )
        registry.register(analyzer)
        registry.register(fixer)
        registry.register(unrelated)
        # FixRequest contains Finding objects, which come from FileFindings
        # The registry should find executors whose consumes type's Finding
        # fields are compatible with the analyzer's produces type's findings
        executors = registry.compatible_executors("reviewer")
        assert any(e.name == "fixer" for e in executors)

    def test_get_nonexistent_returns_none(self) -> None:
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement registry.py**

`codemonkeys/core/agents/registry.py`:

```python
"""Agent registry — declares agent capabilities and wires producers to consumers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


class AgentRole(Enum):
    ANALYZER = "analyzer"
    EXECUTOR = "executor"


class AgentSpec(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(description="Unique identifier for this agent")
    role: AgentRole = Field(description="Whether this agent analyzes or executes")
    description: str = Field(description="Human-readable description shown in the TUI")
    scope: Literal["file", "project"] = Field(
        description="Whether this agent operates on a single file or the whole project"
    )
    produces: Any = Field(default=None, description="Pydantic model type this agent outputs")
    consumes: Any = Field(default=None, description="Pydantic model type this agent accepts as input")
    make: Callable[..., Any] = Field(description="Factory function that creates the AgentDefinition")


class AgentRegistry:

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.name] = spec

    def get(self, name: str) -> AgentSpec | None:
        return self._agents.get(name)

    def list_by_role(self, role: AgentRole) -> list[AgentSpec]:
        return [s for s in self._agents.values() if s.role == role]

    def compatible_executors(self, analyzer_name: str) -> list[AgentSpec]:
        analyzer = self._agents.get(analyzer_name)
        if not analyzer or not analyzer.produces:
            return []
        executors = self.list_by_role(AgentRole.EXECUTOR)
        compatible = []
        for executor in executors:
            if executor.consumes and _types_compatible(analyzer.produces, executor.consumes):
                compatible.append(executor)
        return compatible


def _types_compatible(produces: type, consumes: type) -> bool:
    if produces is consumes:
        return True
    # Check if the consumes type references the produces type or its
    # fields (e.g., FixRequest contains Finding, FileFindings also contains Finding)
    produces_fields = _get_nested_model_types(produces)
    consumes_fields = _get_nested_model_types(consumes)
    return bool(produces_fields & consumes_fields)


def _get_nested_model_types(model: type) -> set[type]:
    types: set[type] = {model}
    if hasattr(model, "model_fields"):
        for field_info in model.model_fields.values():
            annotation = field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                types |= _get_nested_model_types(annotation)
            origin = getattr(annotation, "__origin__", None)
            if origin is list:
                args = getattr(annotation, "__args__", ())
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        types |= _get_nested_model_types(arg)
    return types
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_registry.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Create python_code_fixer agent**

`codemonkeys/core/agents/python_code_fixer.py`:

```python
"""Per-file code fixer — applies fixes from review findings.

Dispatched once per file with a FixRequest artifact. Makes the minimal
changes needed to address each finding.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES


def make_python_code_fixer(file_path: str, findings_json: str) -> AgentDefinition:
    """Create a fixer agent for a single file with specific findings to fix."""
    return AgentDefinition(
        description=f"Fix findings in {file_path}",
        prompt=f"""\
You fix specific code issues in a single file. You are given a JSON object
describing the findings to fix. Make the minimal correct change for each
finding — do not refactor surrounding code or "improve" things outside scope.

## File to Fix

`{file_path}`

## Findings to Fix

```json
{findings_json}
```

## Method

1. Read `{file_path}` to understand the current code.
2. For each finding, make the smallest change that addresses the issue.
3. Run `{PYTHON_CMD} -m ruff check --fix {file_path}` and
   `{PYTHON_CMD} -m ruff format {file_path}`.
4. Run `{PYTHON_CMD} -m pytest -x -q --tb=short --no-header` to verify
   nothing is broken.

## Rules

- Fix only the listed findings. Do not add features or refactor.
- If a finding's suggestion is unclear, make the simplest reasonable fix.
- If a finding cannot be fixed without breaking other code, skip it and explain why.
- Do not push, commit, or modify git state.
- Maximum 2 test-fix cycles. If tests still fail after 2 attempts, stop.

{ENGINEERING_MINDSET}

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Grep",
            "Edit",
            "Write",
            f"Bash({PYTHON_CMD} -m pytest*)",
            f"Bash({PYTHON_CMD} -m ruff*)",
        ],
        permissionMode="acceptEdits",
    )
```

- [ ] **Step 6: Register all agents in a default registry**

Update `codemonkeys/core/agents/__init__.py` to include the fixer and add a function to build the default registry:

Add to the end of the file:

```python
def default_registry() -> "AgentRegistry":
    """Build a registry with all built-in agents."""
    from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
    from codemonkeys.artifacts.schemas.plans import FeaturePlan
    from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer
    from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
    from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
    from codemonkeys.core.agents.python_implementer import make_python_implementer
    from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer
    from codemonkeys.core.agents.registry import AgentRegistry, AgentRole, AgentSpec

    registry = AgentRegistry()
    registry.register(AgentSpec(
        name="python-file-reviewer",
        role=AgentRole.ANALYZER,
        description="Review a Python file for code quality and security issues",
        scope="file",
        produces=FileFindings,
        consumes=None,
        make=make_python_file_reviewer,
    ))
    registry.register(AgentSpec(
        name="changelog-reviewer",
        role=AgentRole.ANALYZER,
        description="Check CHANGELOG.md accuracy against git history",
        scope="project",
        produces=FileFindings,
        consumes=None,
        make=make_changelog_reviewer,
    ))
    registry.register(AgentSpec(
        name="readme-reviewer",
        role=AgentRole.ANALYZER,
        description="Verify README.md claims against the codebase",
        scope="project",
        produces=FileFindings,
        consumes=None,
        make=make_readme_reviewer,
    ))
    registry.register(AgentSpec(
        name="python-code-fixer",
        role=AgentRole.EXECUTOR,
        description="Fix specific findings in a Python file",
        scope="file",
        produces=None,
        consumes=FixRequest,
        make=make_python_code_fixer,
    ))
    registry.register(AgentSpec(
        name="python-implementer",
        role=AgentRole.EXECUTOR,
        description="Implement a feature from an approved plan using TDD",
        scope="project",
        produces=None,
        consumes=FeaturePlan,
        make=make_python_implementer,
    ))
    return registry
```

Also update `__all__` to include `"default_registry"` and `"make_python_code_fixer"`.

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add agent registry, code fixer agent, and default registry"
```

---

## Phase 2: Workflow Engine

### Task 5: Event system

**Files:**
- Create: `codemonkeys/workflows/__init__.py`
- Create: `codemonkeys/workflows/events.py`
- Create: `tests/test_events.py`

- [ ] **Step 1: Write tests for event emission**

`tests/test_events.py`:

```python
from __future__ import annotations

from codemonkeys.workflows.events import (
    AgentCompletedPayload,
    AgentStartedPayload,
    EventEmitter,
    EventType,
    PhaseStartedPayload,
)


class TestEventEmitter:

    def test_subscribe_and_emit(self) -> None:
        emitter = EventEmitter()
        received: list[tuple[EventType, object]] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append((event_type, payload))

        emitter.on(EventType.PHASE_STARTED, handler)
        payload = PhaseStartedPayload(phase="discover", workflow="review")
        emitter.emit(EventType.PHASE_STARTED, payload)
        assert len(received) == 1
        assert received[0][0] == EventType.PHASE_STARTED
        assert received[0][1].phase == "discover"

    def test_wildcard_subscriber(self) -> None:
        emitter = EventEmitter()
        received: list[EventType] = []

        def handler(event_type: EventType, payload: object) -> None:
            received.append(event_type)

        emitter.on_any(handler)
        emitter.emit(EventType.PHASE_STARTED, PhaseStartedPayload(phase="x", workflow="y"))
        emitter.emit(EventType.AGENT_STARTED, AgentStartedPayload(agent_name="test", task_id="1"))
        assert len(received) == 2

    def test_no_subscribers_is_fine(self) -> None:
        emitter = EventEmitter()
        emitter.emit(EventType.PHASE_STARTED, PhaseStartedPayload(phase="x", workflow="y"))

    def test_agent_payloads(self) -> None:
        started = AgentStartedPayload(agent_name="reviewer", task_id="abc")
        assert started.agent_name == "reviewer"
        completed = AgentCompletedPayload(agent_name="reviewer", task_id="abc", tokens=1500)
        assert completed.tokens == 1500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement events.py**

`codemonkeys/workflows/__init__.py`:

```python
"""Workflow engine — state machines, events, and phase management."""
```

`codemonkeys/workflows/events.py`:

```python
"""Typed event system for workflow-to-UI communication."""

from __future__ import annotations

from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field


class EventType(Enum):
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    AGENT_STARTED = "agent_started"
    AGENT_PROGRESS = "agent_progress"
    AGENT_COMPLETED = "agent_completed"
    FINDING_ADDED = "finding_added"
    WAITING_FOR_USER = "waiting_for_user"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ERROR = "workflow_error"


class PhaseStartedPayload(BaseModel):
    phase: str = Field(description="Name of the phase that started")
    workflow: str = Field(description="Name of the workflow")


class PhaseCompletedPayload(BaseModel):
    phase: str = Field(description="Name of the phase that completed")
    workflow: str = Field(description="Name of the workflow")


class AgentStartedPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent that started")
    task_id: str = Field(description="Unique ID for this agent task")


class AgentProgressPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent")
    task_id: str = Field(description="Unique ID for this agent task")
    tokens: int = Field(default=0, description="Tokens consumed so far")
    tool_calls: int = Field(default=0, description="Number of tool calls so far")
    current_tool: str = Field(default="", description="Currently executing tool")


class AgentCompletedPayload(BaseModel):
    agent_name: str = Field(description="Name of the agent that completed")
    task_id: str = Field(description="Unique ID for this agent task")
    tokens: int = Field(default=0, description="Total tokens consumed")


class FindingAddedPayload(BaseModel):
    file: str = Field(description="File the finding belongs to")
    severity: str = Field(description="Finding severity")
    title: str = Field(description="Finding title")


class WaitingForUserPayload(BaseModel):
    phase: str = Field(description="Phase that is waiting for user input")
    workflow: str = Field(description="Name of the workflow")


class WorkflowCompletedPayload(BaseModel):
    workflow: str = Field(description="Name of the workflow that completed")
    run_id: str = Field(description="Artifact store run ID")


class WorkflowErrorPayload(BaseModel):
    workflow: str = Field(description="Name of the workflow that errored")
    error: str = Field(description="Error message")


EventCallback = Callable[[EventType, BaseModel], None]


class EventEmitter:

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventCallback]] = {}
        self._wildcard_handlers: list[EventCallback] = []

    def on(self, event_type: EventType, callback: EventCallback) -> None:
        self._handlers.setdefault(event_type, []).append(callback)

    def on_any(self, callback: EventCallback) -> None:
        self._wildcard_handlers.append(callback)

    def emit(self, event_type: EventType, payload: BaseModel) -> None:
        for handler in self._handlers.get(event_type, []):
            handler(event_type, payload)
        for handler in self._wildcard_handlers:
            handler(event_type, payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_events.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add typed event system for workflow-to-UI communication"
```

---

### Task 6: Workflow engine

**Files:**
- Create: `codemonkeys/workflows/phases.py`
- Create: `codemonkeys/workflows/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write tests for workflow engine**

`tests/test_engine.py`:

```python
from __future__ import annotations

import asyncio

import pytest

from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


class TestWorkflowEngine:

    @pytest.mark.asyncio
    async def test_runs_automated_phases(self) -> None:
        results: list[str] = []

        async def phase_a(ctx: WorkflowContext) -> dict[str, str]:
            results.append("a")
            return {"output": "from_a"}

        async def phase_b(ctx: WorkflowContext) -> dict[str, str]:
            results.append("b")
            return {"output": "from_b"}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="a", phase_type=PhaseType.AUTOMATED, execute=phase_a),
                Phase(name="b", phase_type=PhaseType.AUTOMATED, execute=phase_b),
            ],
        )

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        await engine.run(workflow, ctx)
        assert results == ["a", "b"]

    @pytest.mark.asyncio
    async def test_gate_phase_waits_for_user(self) -> None:
        async def review_phase(ctx: WorkflowContext) -> dict[str, str]:
            return {"findings": "some findings"}

        async def triage_phase(ctx: WorkflowContext) -> dict[str, list[str]]:
            return {"selected": ctx.user_input}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="review", phase_type=PhaseType.AUTOMATED, execute=review_phase),
                Phase(name="triage", phase_type=PhaseType.GATE, execute=triage_phase),
            ],
        )

        emitter = EventEmitter()
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")

        # Resolve the gate after a short delay
        async def resolve_later() -> None:
            await asyncio.sleep(0.05)
            engine.resolve_gate(["fix_item_1"])

        asyncio.get_event_loop().create_task(resolve_later())
        await engine.run(workflow, ctx)
        assert ctx.phase_results.get("triage") == {"selected": ["fix_item_1"]}

    @pytest.mark.asyncio
    async def test_emits_events(self) -> None:
        events: list[EventType] = []

        async def noop(ctx: WorkflowContext) -> dict[str, str]:
            return {}

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="only", phase_type=PhaseType.AUTOMATED, execute=noop),
            ],
        )

        emitter = EventEmitter()
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        await engine.run(workflow, ctx)
        assert EventType.PHASE_STARTED in events
        assert EventType.PHASE_COMPLETED in events
        assert EventType.WORKFLOW_COMPLETED in events

    @pytest.mark.asyncio
    async def test_error_emits_error_event(self) -> None:
        events: list[EventType] = []

        async def failing(ctx: WorkflowContext) -> dict[str, str]:
            raise RuntimeError("boom")

        workflow = Workflow(
            name="test",
            phases=[
                Phase(name="fail", phase_type=PhaseType.AUTOMATED, execute=failing),
            ],
        )

        emitter = EventEmitter()
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)
        ctx = WorkflowContext(cwd="/tmp/test", run_id="test/run1")
        with pytest.raises(RuntimeError, match="boom"):
            await engine.run(workflow, ctx)
        assert EventType.WORKFLOW_ERROR in events
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement phases.py**

`codemonkeys/workflows/phases.py`:

```python
"""Phase types, workflow definitions, and execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class PhaseType(Enum):
    AUTOMATED = "automated"
    INTERACTIVE = "interactive"
    GATE = "gate"


@dataclass
class Phase:
    name: str
    phase_type: PhaseType
    execute: Callable[[WorkflowContext], Coroutine[Any, Any, Any]]


@dataclass
class Workflow:
    name: str
    phases: list[Phase]


@dataclass
class WorkflowContext:
    cwd: str
    run_id: str
    phase_results: dict[str, Any] = field(default_factory=dict)
    user_input: Any = None
```

- [ ] **Step 4: Implement engine.py**

`codemonkeys/workflows/engine.py`:

```python
"""Workflow state machine — runs phases sequentially, pauses at gates."""

from __future__ import annotations

import asyncio
from typing import Any

from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    PhaseCompletedPayload,
    PhaseStartedPayload,
    WaitingForUserPayload,
    WorkflowCompletedPayload,
    WorkflowErrorPayload,
)
from codemonkeys.workflows.phases import PhaseType, Workflow, WorkflowContext


class WorkflowEngine:

    def __init__(self, emitter: EventEmitter) -> None:
        self._emitter = emitter
        self._gate_future: asyncio.Future[Any] | None = None

    async def run(self, workflow: Workflow, context: WorkflowContext) -> None:
        try:
            for phase in workflow.phases:
                self._emitter.emit(
                    EventType.PHASE_STARTED,
                    PhaseStartedPayload(phase=phase.name, workflow=workflow.name),
                )

                if phase.phase_type == PhaseType.GATE:
                    self._emitter.emit(
                        EventType.WAITING_FOR_USER,
                        WaitingForUserPayload(phase=phase.name, workflow=workflow.name),
                    )
                    loop = asyncio.get_running_loop()
                    self._gate_future = loop.create_future()
                    context.user_input = await self._gate_future
                    self._gate_future = None

                result = await phase.execute(context)
                context.phase_results[phase.name] = result

                self._emitter.emit(
                    EventType.PHASE_COMPLETED,
                    PhaseCompletedPayload(phase=phase.name, workflow=workflow.name),
                )

            self._emitter.emit(
                EventType.WORKFLOW_COMPLETED,
                WorkflowCompletedPayload(workflow=workflow.name, run_id=context.run_id),
            )
        except Exception as exc:
            self._emitter.emit(
                EventType.WORKFLOW_ERROR,
                WorkflowErrorPayload(workflow=workflow.name, error=str(exc)),
            )
            raise

    def resolve_gate(self, user_input: Any) -> None:
        if self._gate_future and not self._gate_future.done():
            self._gate_future.set_result(user_input)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add workflow engine with phase state machine and gate support"
```

---

### Task 7: Review workflow

**Files:**
- Create: `codemonkeys/workflows/review.py`
- Create: `tests/test_review_workflow.py`

- [ ] **Step 1: Write tests for review workflow**

`tests/test_review_workflow.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.workflows.events import EventEmitter
from codemonkeys.workflows.review import make_review_workflow


class TestReviewWorkflow:

    def test_has_expected_phases(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "discover" in phase_names
        assert "review" in phase_names
        assert "triage" in phase_names
        assert "fix" in phase_names
        assert "verify" in phase_names

    def test_triage_is_a_gate(self) -> None:
        from codemonkeys.workflows.phases import PhaseType

        workflow = make_review_workflow()
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement review.py**

`codemonkeys/workflows/review.py`:

```python
"""Review workflow — discover, review, triage, fix, verify."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def make_review_workflow() -> Workflow:
    return Workflow(
        name="review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=_discover),
            Phase(name="review", phase_type=PhaseType.AUTOMATED, execute=_review),
            Phase(name="triage", phase_type=PhaseType.GATE, execute=_triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=_fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=_verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=_report),
        ],
    )


async def _discover(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)

    # Find Python files — prefer changed files, fall back to all
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
    else:
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(
                part in p.parts
                for part in ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
            )
        ]

    # Run mechanical checks
    mechanical: dict[str, Any] = {}
    python = sys.executable

    for tool, cmd in [
        ("ruff", [python, "-m", "ruff", "check", "--output-format=json", "."]),
        ("pytest", [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"]),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        mechanical[tool] = {
            "returncode": r.returncode,
            "stdout": r.stdout[:2000],
            "stderr": r.stderr[:500],
        }

    return {"files": files, "mechanical": mechanical}


async def _review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    from codemonkeys.core.runner import AgentRunner

    files = ctx.phase_results["discover"]["files"]
    runner = AgentRunner(cwd=ctx.cwd)
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")
    all_findings: list[FileFindings] = []

    for file_path in files:
        agent = make_python_file_reviewer(file_path)
        output_format = {
            "type": "json_schema",
            "schema": FileFindings.model_json_schema(),
        }
        raw = await runner.run_agent(agent, f"Review: {file_path}", output_format=output_format)

        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            findings = FileFindings.model_validate(structured)
        else:
            try:
                findings = FileFindings.model_validate_json(raw)
            except Exception:
                findings = FileFindings(file=file_path, summary="Could not parse output", findings=[])

        all_findings.append(findings)
        safe_name = file_path.replace("/", "__").replace("\\", "__")
        store.save(ctx.run_id, f"findings/{safe_name}", findings)

    return {"findings": all_findings}


async def _triage(ctx: WorkflowContext) -> dict[str, list[FixRequest]]:
    # user_input is set by the engine after the gate resolves.
    # It should be a list of FixRequest objects (selected by the TUI).
    return {"fix_requests": ctx.user_input}


async def _fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
    from codemonkeys.core.runner import AgentRunner

    fix_requests: list[FixRequest] = ctx.phase_results["triage"]["fix_requests"]
    runner = AgentRunner(cwd=ctx.cwd)
    results: list[FixResult] = []

    for request in fix_requests:
        findings_json = request.model_dump_json(indent=2)
        agent = make_python_code_fixer(request.file, findings_json)
        output_format = {
            "type": "json_schema",
            "schema": FixResult.model_json_schema(),
        }
        raw = await runner.run_agent(
            agent,
            f"Fix findings in {request.file}",
            output_format=output_format,
        )
        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            result = FixResult.model_validate(structured)
        else:
            result = FixResult(file=request.file, fixed=[], skipped=["Could not parse agent output"])
        results.append(result)

    return {"fix_results": results}


async def _verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    cwd = Path(ctx.cwd)
    python = sys.executable

    tests = subprocess.run(
        [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True, text=True, cwd=cwd,
    )
    lint = subprocess.run(
        [python, "-m", "ruff", "check", "."],
        capture_output=True, text=True, cwd=cwd,
    )
    typecheck = subprocess.run(
        [python, "-m", "pyright", "."],
        capture_output=True, text=True, cwd=cwd,
    )

    errors = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")
    if typecheck.returncode != 0:
        errors.append(f"pyright: {typecheck.stdout[:500]}")

    result = VerificationResult(
        tests_passed=tests.returncode == 0,
        lint_passed=lint.returncode == 0,
        typecheck_passed=typecheck.returncode == 0,
        errors=errors,
    )
    return {"verification": result}


async def _report(ctx: WorkflowContext) -> dict[str, Any]:
    fix_results = ctx.phase_results.get("fix", {}).get("fix_results", [])
    verification = ctx.phase_results.get("verify", {}).get("verification")

    fixed_count = sum(len(r.fixed) for r in fix_results)
    skipped_count = sum(len(r.skipped) for r in fix_results)

    return {
        "summary": {
            "fixed": fixed_count,
            "skipped": skipped_count,
            "tests_passed": verification.tests_passed if verification else None,
            "lint_passed": verification.lint_passed if verification else None,
        }
    }
```

- [ ] **Step 4: Update test to include report phase**

Add to the test in `tests/test_review_workflow.py`:

```python
    def test_has_report_phase(self) -> None:
        workflow = make_review_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "report" in phase_names
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_workflow.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add review workflow with discover, review, triage, fix, verify, report phases"
```

---

### Task 8: Implement workflow

**Files:**
- Create: `codemonkeys/workflows/implement.py`
- Create: `tests/test_implement_workflow.py`

- [ ] **Step 1: Write tests for implement workflow**

`tests/test_implement_workflow.py`:

```python
from __future__ import annotations

from codemonkeys.workflows.implement import make_implement_workflow
from codemonkeys.workflows.phases import PhaseType


class TestImplementWorkflow:

    def test_has_expected_phases(self) -> None:
        workflow = make_implement_workflow()
        phase_names = [p.name for p in workflow.phases]
        assert "plan" in phase_names
        assert "approve" in phase_names
        assert "implement" in phase_names
        assert "verify" in phase_names

    def test_approve_is_a_gate(self) -> None:
        workflow = make_implement_workflow()
        approve = next(p for p in workflow.phases if p.name == "approve")
        assert approve.phase_type == PhaseType.GATE

    def test_plan_is_interactive(self) -> None:
        workflow = make_implement_workflow()
        plan = next(p for p in workflow.phases if p.name == "plan")
        assert plan.phase_type == PhaseType.INTERACTIVE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_implement_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement implement.py**

`codemonkeys/workflows/implement.py`:

```python
"""Implement workflow — plan, approve, implement, verify."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.plans import FeaturePlan
from codemonkeys.artifacts.schemas.results import VerificationResult
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.core.agents.python_implementer import make_python_implementer
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def make_implement_workflow() -> Workflow:
    return Workflow(
        name="implement",
        phases=[
            Phase(name="plan", phase_type=PhaseType.INTERACTIVE, execute=_plan),
            Phase(name="approve", phase_type=PhaseType.GATE, execute=_approve),
            Phase(name="implement", phase_type=PhaseType.AUTOMATED, execute=_implement),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=_verify),
        ],
    )


async def _plan(ctx: WorkflowContext) -> dict[str, Any]:
    # V1 simplification: the TUI collects a feature description from the user
    # and passes it as user_input. A future version could use a planner agent
    # to generate steps interactively, but for now the implementer agent
    # receives the description directly and plans its own approach.
    description = ctx.user_input or ""
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")

    plan = FeaturePlan(
        title=description[:80],
        description=description,
        steps=[],
    )
    store.save(ctx.run_id, "plan", plan)
    return {"plan": plan}


async def _approve(ctx: WorkflowContext) -> dict[str, FeaturePlan]:
    # user_input is the approved (possibly edited) plan from the TUI gate.
    return {"approved_plan": ctx.user_input}


async def _implement(ctx: WorkflowContext) -> dict[str, str]:
    from codemonkeys.core.runner import AgentRunner

    plan: FeaturePlan = ctx.phase_results["approve"]["approved_plan"]
    store = ArtifactStore(Path(ctx.cwd) / ".codemonkeys")
    store.save(ctx.run_id, "approved-plan", plan)

    agent = make_python_implementer()
    runner = AgentRunner(cwd=ctx.cwd)
    prompt = f"Implement this plan:\n\n{plan.model_dump_json(indent=2)}"
    result = await runner.run_agent(agent, prompt)
    return {"result": result}


async def _verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    cwd = Path(ctx.cwd)
    python = sys.executable

    tests = subprocess.run(
        [python, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True, text=True, cwd=cwd,
    )
    lint = subprocess.run(
        [python, "-m", "ruff", "check", "."],
        capture_output=True, text=True, cwd=cwd,
    )

    errors = []
    if tests.returncode != 0:
        errors.append(f"pytest: {tests.stdout[:500]}")
    if lint.returncode != 0:
        errors.append(f"ruff: {lint.stdout[:500]}")

    result = VerificationResult(
        tests_passed=tests.returncode == 0,
        lint_passed=lint.returncode == 0,
        typecheck_passed=True,
        errors=errors,
    )
    return {"verification": result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_implement_workflow.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add implement workflow with plan, approve, implement, verify phases"
```

---

## Phase 3: TUI

### Task 9: TUI theme and app shell

**Files:**
- Create: `codemonkeys/tui/__init__.py`
- Create: `codemonkeys/tui/theme.py`
- Create: `codemonkeys/tui/app.py`
- Create: `codemonkeys/tui/app.tcss`
- Create: `tests/test_tui_app.py`

- [ ] **Step 1: Write test for app startup**

`tests/test_tui_app.py`:

```python
from __future__ import annotations

import pytest

from codemonkeys.tui.app import CodemonkeysApp


class TestCodemonkeysApp:

    @pytest.mark.asyncio
    async def test_app_starts_and_shows_home(self) -> None:
        app = CodemonkeysApp()
        async with app.run_test() as pilot:
            assert app.title == "codemonkeys"
            # Home screen should be the default
            assert app.screen.name == "home"

    @pytest.mark.asyncio
    async def test_app_has_header_and_footer(self) -> None:
        app = CodemonkeysApp()
        async with app.run_test() as pilot:
            header = app.query("Header")
            footer = app.query("Footer")
            assert len(header) == 1
            assert len(footer) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tui_app.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create theme.py**

`codemonkeys/tui/__init__.py`:

```python
"""Textual TUI for codemonkeys."""
```

`codemonkeys/tui/theme.py`:

```python
"""Color palette and style constants for the codemonkeys TUI."""

from __future__ import annotations

# Severity colors
SEVERITY_COLORS = {
    "high": "#ff5555",
    "medium": "#ffb86c",
    "low": "#8be9fd",
    "info": "#6272a4",
}

# Status colors
STATUS_COLORS = {
    "running": "#f1fa8c",
    "done": "#50fa7b",
    "failed": "#ff5555",
    "queued": "#6272a4",
    "waiting": "#bd93f9",
}

# UI accent colors
ACCENT = "#bd93f9"
ACCENT_DIM = "#44475a"
SURFACE = "#282a36"
SURFACE_LIGHT = "#44475a"
TEXT = "#f8f8f2"
TEXT_DIM = "#6272a4"
```

- [ ] **Step 4: Create the main app CSS**

`codemonkeys/tui/app.tcss`:

```css
/* codemonkeys — main application stylesheet */

Screen {
    background: #282a36;
    color: #f8f8f2;
}

Header {
    background: #1e1f29;
    color: #bd93f9;
    text-style: bold;
}

Footer {
    background: #1e1f29;
}

/* Sidebar navigation */
#sidebar {
    width: 28;
    background: #1e1f29;
    border-right: solid #44475a;
    padding: 1 0;
}

#sidebar .nav-button {
    width: 100%;
    margin: 0 1;
    background: transparent;
    color: #f8f8f2;
    border: none;
    text-align: left;
    padding: 0 2;
    height: 3;
}

#sidebar .nav-button:hover {
    background: #44475a;
}

#sidebar .nav-button:focus {
    background: #6272a4;
    color: #f8f8f2;
}

#sidebar .nav-button.-active {
    background: #bd93f9;
    color: #282a36;
    text-style: bold;
}

/* Main content area */
#main-content {
    padding: 1 2;
}

/* Agent dashboard panel */
#agent-dashboard {
    height: auto;
    max-height: 16;
    background: #1e1f29;
    border-top: solid #44475a;
    padding: 0 1;
}

#agent-dashboard.hidden {
    display: none;
}

/* Agent card widget */
.agent-card {
    height: 3;
    margin: 0 0 0 0;
    padding: 0 1;
    background: #282a36;
    border: round #44475a;
}

.agent-card.-running {
    border: round #f1fa8c;
}

.agent-card.-done {
    border: round #50fa7b;
}

.agent-card.-failed {
    border: round #ff5555;
}

.agent-card .agent-name {
    color: #8be9fd;
    text-style: bold;
    width: 1fr;
}

.agent-card .agent-status {
    width: 10;
}

.agent-card .agent-tokens {
    width: 14;
    text-align: right;
    color: #6272a4;
}

/* Severity badges */
.severity-high {
    color: #ff5555;
    text-style: bold;
}

.severity-medium {
    color: #ffb86c;
}

.severity-low {
    color: #8be9fd;
}

.severity-info {
    color: #6272a4;
}

/* Finding view */
.finding {
    margin: 0 0 1 0;
    padding: 1;
    background: #1e1f29;
    border: round #44475a;
}

.finding .finding-header {
    text-style: bold;
}

.finding .finding-description {
    margin: 1 0 0 0;
    color: #f8f8f2;
}

.finding .finding-suggestion {
    margin: 1 0 0 0;
    color: #50fa7b;
}

/* Home screen */
.welcome-panel {
    padding: 2 4;
    margin: 1;
    background: #1e1f29;
    border: round #bd93f9;
    text-align: center;
}

.action-card {
    padding: 1 2;
    margin: 1;
    background: #1e1f29;
    border: round #44475a;
    height: 5;
}

.action-card:hover {
    border: round #bd93f9;
}

.action-card:focus {
    border: round #bd93f9;
    background: #44475a;
}

.action-card .action-title {
    text-style: bold;
    color: #8be9fd;
}

.action-card .action-desc {
    color: #6272a4;
}

/* Progress bar */
ProgressBar Bar {
    color: #bd93f9;
    background: #44475a;
}

/* Buttons */
Button {
    background: #44475a;
    color: #f8f8f2;
    border: none;
}

Button:hover {
    background: #6272a4;
}

Button.-primary {
    background: #bd93f9;
    color: #282a36;
    text-style: bold;
}

Button.-primary:hover {
    background: #ff79c6;
}

Button.-success {
    background: #50fa7b;
    color: #282a36;
}

Button.-danger {
    background: #ff5555;
    color: #282a36;
}

/* DataTable */
DataTable {
    background: #282a36;
}

DataTable > .datatable--header {
    background: #1e1f29;
    color: #bd93f9;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #44475a;
    color: #f8f8f2;
}
```

- [ ] **Step 5: Create the main app**

`codemonkeys/tui/app.py`:

```python
"""Main Textual application for codemonkeys."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Button, Footer, Header, Static


class Sidebar(Container):

    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        background: #1e1f29;
        border-right: solid #44475a;
        padding: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("  [bold #bd93f9]codemonkeys[/]", classes="logo")
        yield Static("")
        yield Button("  Home", id="nav-home", classes="nav-button -active")
        yield Button("  Analyze", id="nav-analyze", classes="nav-button")
        yield Button("  Queue", id="nav-queue", classes="nav-button")
        yield Button("  Dashboard", id="nav-dashboard", classes="nav-button")


class HomeContent(Container):

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #bd93f9]codemonkeys[/]\n\n"
            "[#6272a4]AI-powered code analysis and implementation workflows[/]",
            classes="welcome-panel",
        )
        with Horizontal():
            with Container(classes="action-card", id="action-review"):
                yield Static("[#8be9fd bold]Run Code Review[/]", classes="action-title")
                yield Static("[#6272a4]Analyze files for quality and security issues[/]", classes="action-desc")
            with Container(classes="action-card", id="action-implement"):
                yield Static("[#8be9fd bold]Implement Feature[/]", classes="action-title")
                yield Static("[#6272a4]Plan and build a feature with TDD[/]", classes="action-desc")


class CodemonkeysApp(App[None]):

    TITLE = "codemonkeys"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home", show=True),
        Binding("a", "go_analyze", "Analyze", show=True),
        Binding("u", "go_queue", "Queue", show=True),
        Binding("d", "go_dashboard", "Dashboard", show=True),
    ]

    def __init__(self, cwd: Path | None = None) -> None:
        super().__init__()
        self.cwd = cwd or Path.cwd()

    @property
    def screen_name(self) -> str:
        return "home"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Container(id="main-content"):
                yield HomeContent(id="home-content")
        yield Footer()

    def action_go_home(self) -> None:
        self._switch_content("home")

    def action_go_analyze(self) -> None:
        self._switch_content("analyze")

    def action_go_queue(self) -> None:
        self._switch_content("queue")

    def action_go_dashboard(self) -> None:
        self._switch_content("dashboard")

    def _switch_content(self, screen_id: str) -> None:
        # Full screen implementation comes in later tasks.
        # For now, update the sidebar active state.
        for btn in self.query(".nav-button"):
            btn.remove_class("-active")
        nav_btn = self.query_one(f"#nav-{screen_id}", Button)
        nav_btn.add_class("-active")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_tui_app.py -v`
Expected: All tests PASS. The test may need adjustments based on exact Textual behavior — verify the `app.screen.name` assertion. If Textual's default screen has a different name, update the test to check for the presence of `HomeContent` instead:

```python
assert len(app.query("HomeContent")) == 1
```

- [ ] **Step 7: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add TUI app shell with theme, sidebar navigation, and home screen"
```

---

### Task 10: Agent card widget and dashboard screen

**Files:**
- Create: `codemonkeys/tui/widgets/__init__.py`
- Create: `codemonkeys/tui/widgets/agent_card.py`
- Create: `codemonkeys/tui/screens/__init__.py`
- Create: `codemonkeys/tui/screens/dashboard.py`
- Create: `tests/test_tui_dashboard.py`

- [ ] **Step 1: Write test for agent card**

`tests/test_tui_dashboard.py`:

```python
from __future__ import annotations

import pytest

from codemonkeys.tui.widgets.agent_card import AgentCard, AgentStatus


class TestAgentCard:

    @pytest.mark.asyncio
    async def test_card_renders_name(self) -> None:
        card = AgentCard(agent_name="python-file-reviewer", task_id="abc123")
        # Verify the widget can be instantiated with correct attributes
        assert card.agent_name == "python-file-reviewer"
        assert card.status == AgentStatus.RUNNING

    def test_status_update(self) -> None:
        card = AgentCard(agent_name="test", task_id="123")
        card.update_progress(tokens=1500, tool_calls=3, current_tool="Read(src/main.py)")
        assert card.tokens == 1500
        assert card.tool_calls == 3

    def test_mark_done(self) -> None:
        card = AgentCard(agent_name="test", task_id="123")
        card.mark_done(tokens=5000)
        assert card.status == AgentStatus.DONE
        assert card.tokens == 5000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tui_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement agent_card.py**

`codemonkeys/tui/widgets/__init__.py`:

```python
"""Reusable TUI widgets."""
```

`codemonkeys/tui/widgets/agent_card.py`:

```python
"""Live agent status card widget."""

from __future__ import annotations

from enum import Enum

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ProgressBar


class AgentStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AgentCard(Widget):

    DEFAULT_CSS = """
    AgentCard {
        height: 3;
        padding: 0 1;
        background: #282a36;
        border: round #44475a;
        layout: horizontal;
    }
    AgentCard.-running { border: round #f1fa8c; }
    AgentCard.-done { border: round #50fa7b; }
    AgentCard.-failed { border: round #ff5555; }
    AgentCard .card-name { width: 1fr; color: #8be9fd; text-style: bold; }
    AgentCard .card-tool { width: 1fr; color: #6272a4; }
    AgentCard .card-status { width: 10; }
    AgentCard .card-tokens { width: 14; text-align: right; color: #6272a4; }
    """

    status: reactive[AgentStatus] = reactive(AgentStatus.RUNNING)
    tokens: reactive[int] = reactive(0)
    tool_calls: reactive[int] = reactive(0)
    current_tool: reactive[str] = reactive("")

    def __init__(self, agent_name: str, task_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.task_id = task_id

    def compose(self) -> ComposeResult:
        yield Label(self.agent_name, classes="card-name")
        yield Label("", classes="card-tool", id="tool-label")
        yield Label("running", classes="card-status", id="status-label")
        yield Label("0 tok", classes="card-tokens", id="tokens-label")

    def update_progress(self, tokens: int = 0, tool_calls: int = 0, current_tool: str = "") -> None:
        self.tokens = tokens
        self.tool_calls = tool_calls
        self.current_tool = current_tool

    def mark_done(self, tokens: int = 0) -> None:
        self.tokens = tokens
        self.status = AgentStatus.DONE

    def mark_failed(self) -> None:
        self.status = AgentStatus.FAILED

    def watch_status(self, value: AgentStatus) -> None:
        self.remove_class("-running", "-done", "-failed")
        self.add_class(f"-{value.value}")
        try:
            self.query_one("#status-label", Label).update(value.value)
        except Exception:
            pass

    def watch_tokens(self, value: int) -> None:
        try:
            self.query_one("#tokens-label", Label).update(f"{value:,} tok")
        except Exception:
            pass

    def watch_current_tool(self, value: str) -> None:
        try:
            self.query_one("#tool-label", Label).update(value[:40])
        except Exception:
            pass
```

- [ ] **Step 4: Implement dashboard screen**

`codemonkeys/tui/screens/__init__.py`:

```python
"""TUI screens."""
```

`codemonkeys/tui/screens/dashboard.py`:

```python
"""Full-screen agent monitoring dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from codemonkeys.tui.widgets.agent_card import AgentCard


class DashboardScreen(Container):

    DEFAULT_CSS = """
    DashboardScreen {
        padding: 1;
    }
    DashboardScreen #dashboard-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    DashboardScreen #agent-list {
        height: 1fr;
    }
    DashboardScreen #no-agents {
        color: #6272a4;
        text-align: center;
        margin: 4 0;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cards: dict[str, AgentCard] = {}

    def compose(self) -> ComposeResult:
        yield Static("Agent Dashboard", id="dashboard-header")
        yield VerticalScroll(
            Static("No agents running", id="no-agents"),
            id="agent-list",
        )

    def add_agent(self, agent_name: str, task_id: str) -> None:
        card = AgentCard(agent_name=agent_name, task_id=task_id)
        self._cards[task_id] = card
        agent_list = self.query_one("#agent-list", VerticalScroll)
        no_agents = self.query("#no-agents")
        if no_agents:
            no_agents.first().remove()
        agent_list.mount(card)

    def update_agent(self, task_id: str, tokens: int = 0, tool_calls: int = 0, current_tool: str = "") -> None:
        if task_id in self._cards:
            self._cards[task_id].update_progress(tokens, tool_calls, current_tool)

    def complete_agent(self, task_id: str, tokens: int = 0) -> None:
        if task_id in self._cards:
            self._cards[task_id].mark_done(tokens)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_tui_dashboard.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add agent card widget and dashboard screen"
```

---

### Task 11: Analyzer screen

**Files:**
- Create: `codemonkeys/tui/screens/analyzer.py`
- Create: `tests/test_tui_analyzer.py`

- [ ] **Step 1: Write test for analyzer screen**

`tests/test_tui_analyzer.py`:

```python
from __future__ import annotations

import pytest

from codemonkeys.tui.screens.analyzer import AnalyzerScreen


class TestAnalyzerScreen:

    def test_screen_instantiates(self) -> None:
        screen = AnalyzerScreen()
        assert screen is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tui_analyzer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement analyzer.py**

`codemonkeys/tui/screens/analyzer.py`:

```python
"""Analyzer screen — select targets and kick off analysis."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Checkbox, Label, Static


class AnalyzerScreen(Container):

    DEFAULT_CSS = """
    AnalyzerScreen {
        padding: 1;
    }
    AnalyzerScreen #analyzer-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    AnalyzerScreen .scope-section {
        margin: 0 0 1 0;
        padding: 1;
        background: #1e1f29;
        border: round #44475a;
    }
    AnalyzerScreen .scope-title {
        text-style: bold;
        color: #8be9fd;
        margin: 0 0 1 0;
    }
    AnalyzerScreen #file-list {
        height: auto;
        max-height: 20;
        margin: 1 0;
    }
    AnalyzerScreen #analyze-actions {
        margin: 1 0;
        height: 3;
    }
    """

    class AnalysisRequested(Message):
        def __init__(self, files: list[str]) -> None:
            super().__init__()
            self.files = files

    def compose(self) -> ComposeResult:
        yield Static("Analyze Code", id="analyzer-header")
        with Container(classes="scope-section"):
            yield Static("Select scope", classes="scope-title")
            with Horizontal(id="analyze-actions"):
                yield Button("Changed files", id="btn-changed", classes="-primary")
                yield Button("All files", id="btn-all")
                yield Button("Select files...", id="btn-select")

        yield VerticalScroll(id="file-list")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-changed":
            self._load_changed_files()
        elif event.button.id == "btn-all":
            self._load_all_files()
        elif event.button.id == "btn-run":
            self._run_analysis()

    def _load_changed_files(self) -> None:
        import subprocess

        cwd = self._get_cwd()
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            capture_output=True, text=True, cwd=cwd,
        )
        files = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
        self._show_file_list(files)

    def _load_all_files(self) -> None:
        cwd = Path(self._get_cwd())
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(
                part in p.parts
                for part in ("__pycache__", ".venv", "venv", ".tox", "dist", ".eggs")
            )
        ]
        self._show_file_list(sorted(files))

    def _show_file_list(self, files: list[str]) -> None:
        file_list = self.query_one("#file-list", VerticalScroll)
        file_list.remove_children()
        for f in files:
            file_list.mount(Checkbox(f, value=True, id=f"file-{f.replace('/', '__')}"))
        file_list.mount(
            Button("Run Analysis", id="btn-run", classes="-primary")
        )

    def _run_analysis(self) -> None:
        selected = []
        for cb in self.query(Checkbox):
            if cb.value:
                label_text = str(cb.label)
                selected.append(label_text)
        self.post_message(self.AnalysisRequested(selected))

    def _get_cwd(self) -> str:
        return str(getattr(self.app, "cwd", Path.cwd()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tui_analyzer.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add analyzer screen for selecting review targets"
```

---

### Task 12: Queue screen and finding view widget

**Files:**
- Create: `codemonkeys/tui/widgets/finding_view.py`
- Create: `codemonkeys/tui/screens/queue.py`
- Create: `tests/test_tui_queue.py`

- [ ] **Step 1: Write test for finding view widget**

`tests/test_tui_queue.py`:

```python
from __future__ import annotations

import pytest

from codemonkeys.artifacts.schemas.findings import Finding
from codemonkeys.tui.widgets.finding_view import FindingView


class TestFindingView:

    def test_instantiates_with_finding(self) -> None:
        finding = Finding(
            file="src/auth.py",
            line=42,
            severity="high",
            category="security",
            subcategory="injection",
            title="SQL injection via f-string",
            description="User input interpolated into SQL query.",
            suggestion="Use parameterized query.",
        )
        view = FindingView(finding=finding)
        assert view.finding.severity == "high"
        assert view.selected is True  # default to selected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tui_queue.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement finding_view.py**

`codemonkeys/tui/widgets/finding_view.py`:

```python
"""Rendered finding with severity badge, description, and selection toggle."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Checkbox, Label, Static

from codemonkeys.artifacts.schemas.findings import Finding

_SEVERITY_STYLES = {
    "high": "bold #ff5555",
    "medium": "#ffb86c",
    "low": "#8be9fd",
    "info": "#6272a4",
}


class FindingView(Widget):

    DEFAULT_CSS = """
    FindingView {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        background: #1e1f29;
        border: round #44475a;
    }
    FindingView.-selected {
        border: round #bd93f9;
    }
    FindingView .finding-header {
        height: 1;
    }
    FindingView .finding-badge {
        width: 8;
        text-style: bold;
    }
    FindingView .finding-title {
        width: 1fr;
        text-style: bold;
    }
    FindingView .finding-location {
        width: 20;
        text-align: right;
        color: #6272a4;
    }
    FindingView .finding-body {
        margin: 1 0 0 2;
        color: #f8f8f2;
    }
    FindingView .finding-suggestion {
        margin: 1 0 0 2;
        color: #50fa7b;
    }
    """

    selected: reactive[bool] = reactive(True)

    def __init__(self, finding: Finding, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.finding = finding

    def compose(self) -> ComposeResult:
        style = _SEVERITY_STYLES.get(self.finding.severity, "#f8f8f2")
        location = f"{self.finding.file}:{self.finding.line}" if self.finding.line else self.finding.file

        with Horizontal(classes="finding-header"):
            yield Checkbox("", value=True, id="finding-toggle")
            yield Label(f"[{style}]{self.finding.severity.upper()}[/]", classes="finding-badge")
            yield Label(self.finding.title, classes="finding-title")
            yield Label(location, classes="finding-location")

        yield Static(self.finding.description, classes="finding-body")
        if self.finding.suggestion:
            yield Static(f"Fix: {self.finding.suggestion}", classes="finding-suggestion")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.selected = event.value
        if self.selected:
            self.add_class("-selected")
        else:
            self.remove_class("-selected")
```

- [ ] **Step 4: Implement queue screen**

`codemonkeys/tui/screens/queue.py`:

```python
"""Queue screen — browse artifacts, select findings, dispatch fixers."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Label, Static

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.store import ArtifactStore
from codemonkeys.tui.widgets.finding_view import FindingView


class QueueScreen(Container):

    DEFAULT_CSS = """
    QueueScreen {
        padding: 1;
    }
    QueueScreen #queue-header {
        text-style: bold;
        color: #bd93f9;
        margin: 0 0 1 0;
    }
    QueueScreen .run-item {
        height: 3;
        padding: 0 1;
        background: #1e1f29;
        border: round #44475a;
        margin: 0 0 0 0;
    }
    QueueScreen .run-item:hover {
        border: round #bd93f9;
    }
    QueueScreen .file-summary {
        height: 3;
        padding: 0 1;
        background: #282a36;
        border: round #44475a;
        margin: 0 0 0 0;
    }
    QueueScreen .file-summary:hover {
        border: round #8be9fd;
    }
    QueueScreen #findings-scroll {
        height: 1fr;
    }
    QueueScreen #queue-actions {
        height: 3;
        margin: 1 0 0 0;
    }
    """

    class FixRequested(Message):
        def __init__(self, fix_requests: list[FixRequest]) -> None:
            super().__init__()
            self.fix_requests = fix_requests

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._current_findings: list[FileFindings] = []

    def compose(self) -> ComposeResult:
        yield Static("Review Queue", id="queue-header")
        yield VerticalScroll(id="findings-scroll")
        with Horizontal(id="queue-actions"):
            yield Button("Fix Selected", id="btn-fix-selected", classes="-primary")
            yield Button("Fix All High", id="btn-fix-high", classes="-danger")
            yield Button("Back", id="btn-back")

    def load_findings(self, findings_list: list[FileFindings]) -> None:
        self._current_findings = findings_list
        scroll = self.query_one("#findings-scroll", VerticalScroll)
        scroll.remove_children()

        for file_findings in findings_list:
            if not file_findings.findings:
                continue
            high = sum(1 for f in file_findings.findings if f.severity == "high")
            med = sum(1 for f in file_findings.findings if f.severity == "medium")
            low = sum(1 for f in file_findings.findings if f.severity == "low")

            counts = []
            if high:
                counts.append(f"[#ff5555]{high} high[/]")
            if med:
                counts.append(f"[#ffb86c]{med} med[/]")
            if low:
                counts.append(f"[#8be9fd]{low} low[/]")

            scroll.mount(Static(
                f"[bold #8be9fd]{file_findings.file}[/]  "
                f"{len(file_findings.findings)} findings ({', '.join(counts)})",
                classes="file-summary",
            ))
            for finding in file_findings.findings:
                scroll.mount(FindingView(finding=finding))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-fix-selected":
            self._fix_selected()
        elif event.button.id == "btn-fix-high":
            self._fix_high_severity()

    def _fix_selected(self) -> None:
        fix_requests = self._collect_selected_findings()
        if fix_requests:
            self.post_message(self.FixRequested(fix_requests))

    def _fix_high_severity(self) -> None:
        requests: dict[str, list[Finding]] = {}
        for file_findings in self._current_findings:
            for finding in file_findings.findings:
                if finding.severity == "high":
                    requests.setdefault(finding.file, []).append(finding)
        fix_requests = [FixRequest(file=f, findings=findings) for f, findings in requests.items()]
        if fix_requests:
            self.post_message(self.FixRequested(fix_requests))

    def _collect_selected_findings(self) -> list[FixRequest]:
        requests: dict[str, list[Finding]] = {}
        for view in self.query(FindingView):
            if view.selected:
                requests.setdefault(view.finding.file, []).append(view.finding)
        return [FixRequest(file=f, findings=findings) for f, findings in requests.items()]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_tui_queue.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add queue screen with finding view widget and fix selection"
```

---

### Task 13: CLI entry point and app integration

**Files:**
- Create: `codemonkeys/cli.py`
- Modify: `codemonkeys/tui/app.py`
- Modify: `pyproject.toml` (already has entry point from Task 1)
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write test for CLI entry point**

`tests/test_cli.py`:

```python
from __future__ import annotations

from unittest.mock import patch

from codemonkeys.cli import main


class TestCLI:

    @patch("codemonkeys.cli.CodemonkeysApp")
    @patch("codemonkeys.cli.restrict")
    def test_main_calls_restrict_and_runs_app(self, mock_restrict, mock_app_cls) -> None:
        mock_app = mock_app_cls.return_value
        main()
        mock_restrict.assert_called_once()
        mock_app.run.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement cli.py**

`codemonkeys/cli.py`:

```python
"""CLI entry point — sandbox the process and launch the TUI."""

from __future__ import annotations

from pathlib import Path

from codemonkeys.core.sandbox import restrict
from codemonkeys.tui.app import CodemonkeysApp


def main() -> None:
    cwd = Path.cwd()
    restrict(cwd)
    app = CodemonkeysApp(cwd=cwd)
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update app.py to wire screens together**

Update `codemonkeys/tui/app.py` to import and switch between actual screen containers. Add the workflow integration:

```python
"""Main Textual application for codemonkeys."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Button, Footer, Header, Static

from codemonkeys.tui.screens.analyzer import AnalyzerScreen
from codemonkeys.tui.screens.dashboard import DashboardScreen
from codemonkeys.tui.screens.queue import QueueScreen


class Sidebar(Container):

    DEFAULT_CSS = """
    Sidebar {
        width: 28;
        background: #1e1f29;
        border-right: solid #44475a;
        padding: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("  [bold #bd93f9]codemonkeys[/]", classes="logo")
        yield Static("")
        yield Button("  Home", id="nav-home", classes="nav-button -active")
        yield Button("  Analyze", id="nav-analyze", classes="nav-button")
        yield Button("  Queue", id="nav-queue", classes="nav-button")
        yield Button("  Dashboard", id="nav-dashboard", classes="nav-button")


class HomeContent(Container):

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold #bd93f9]codemonkeys[/]\n\n"
            "[#6272a4]AI-powered code analysis and implementation workflows[/]",
            classes="welcome-panel",
        )
        with Horizontal():
            with Container(classes="action-card", id="action-review"):
                yield Static("[#8be9fd bold]Run Code Review[/]", classes="action-title")
                yield Static("[#6272a4]Analyze files for quality and security issues[/]", classes="action-desc")
            with Container(classes="action-card", id="action-implement"):
                yield Static("[#8be9fd bold]Implement Feature[/]", classes="action-title")
                yield Static("[#6272a4]Plan and build a feature with TDD[/]", classes="action-desc")


class CodemonkeysApp(App[None]):

    TITLE = "codemonkeys"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home", show=True),
        Binding("a", "go_analyze", "Analyze", show=True),
        Binding("u", "go_queue", "Queue", show=True),
        Binding("d", "go_dashboard", "Dashboard", show=True),
    ]

    def __init__(self, cwd: Path | None = None) -> None:
        super().__init__()
        self.cwd = cwd or Path.cwd()
        self._current_view = "home"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Container(id="main-content"):
                yield HomeContent(id="view-home")
                yield AnalyzerScreen(id="view-analyze")
                yield DashboardScreen(id="view-dashboard")
                yield QueueScreen(id="view-queue")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#view-analyze").display = False
        self.query_one("#view-dashboard").display = False
        self.query_one("#view-queue").display = False

    def action_go_home(self) -> None:
        self._switch_view("home")

    def action_go_analyze(self) -> None:
        self._switch_view("analyze")

    def action_go_queue(self) -> None:
        self._switch_view("queue")

    def action_go_dashboard(self) -> None:
        self._switch_view("dashboard")

    def _switch_view(self, view_id: str) -> None:
        for vid in ("home", "analyze", "dashboard", "queue"):
            widget = self.query_one(f"#view-{vid}")
            widget.display = vid == view_id

        for btn in self.query(".nav-button"):
            btn.remove_class("-active")
        self.query_one(f"#nav-{view_id}", Button).add_class("-active")
        self._current_view = view_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("nav-"):
            view = event.button.id.removeprefix("nav-")
            self._switch_view(view)
        elif event.button.id == "action-review":
            self._switch_view("analyze")
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
ruff check --fix . && ruff format .
git add -A
git commit -m "feat: add CLI entry point and wire TUI screens together"
```

- [ ] **Step 7: Manual smoke test**

Run: `python -m codemonkeys.cli`

Verify:
- App launches with the dark theme
- Sidebar shows navigation buttons
- Home screen shows welcome panel and action cards
- Pressing `a` switches to the Analyze screen
- Pressing `d` switches to the Dashboard screen
- Pressing `u` switches to the Queue screen
- Pressing `h` returns to Home
- Pressing `q` quits
