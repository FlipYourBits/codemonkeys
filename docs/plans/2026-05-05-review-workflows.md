# Review Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement four composable review workflows (full repo, diff, files, post-feature) using a shared phase library, one new agent (spec_compliance_reviewer), mechanical audit tooling, and event system extensions.

**Architecture:** Phase library + per-mode composition. Reusable async phase functions are assembled into workflow definitions. Mechanical tools (ruff, pyright, pytest, pip-audit, secrets grep, coverage map, dead code detection) run as subprocess calls in a parameterized audit phase. Agents receive pre-computed mechanical data as context and focus on judgment.

**Tech Stack:** Python 3.12+, Pydantic v2, asyncio, Claude Agent SDK, pytest, ruff, pyright

---

## File Structure

```
codemonkeys/
  artifacts/schemas/
    mechanical.py                  # NEW — mechanical audit result schemas
    spec_compliance.py             # NEW — SpecComplianceFindings schema
    __init__.py                    # MODIFY — add new schema exports
  core/
    agents/
      spec_compliance_reviewer.py  # NEW — agent factory
      __init__.py                  # MODIFY — add new agent to exports + registry
    prompts/
      hardening_checklist.py       # NEW — post-feature architecture prompt
      diff_context.py              # NEW — diff mode file reviewer prompt template
      __init__.py                  # MODIFY — export new prompts
  workflows/
    phase_library/                 # NEW directory
      __init__.py                  # re-export all phases
      discovery.py                 # discover_all_files, discover_diff, discover_files, discover_from_spec
      mechanical.py                # mechanical_audit + individual tool runners
      review.py                    # file_review, architecture_review, doc_review, spec_compliance_review
      action.py                    # triage, fix, verify, report
    compositions.py                # NEW — ReviewConfig + 4 workflow builders
    events.py                      # MODIFY — add new event types + payloads
    phases.py                      # MODIFY — add config to WorkflowContext
tests/
  test_mechanical_schemas.py       # NEW
  test_spec_compliance_schemas.py  # NEW
  test_compositions.py             # NEW
  test_discovery_phases.py         # NEW
  test_mechanical_phase.py         # NEW
  test_review_phases.py            # NEW
  test_action_phases.py            # NEW
  test_new_events.py               # NEW
  test_spec_compliance_reviewer.py # NEW
```

---

### Task 1: Mechanical Audit Schemas

**Files:**
- Create: `codemonkeys/artifacts/schemas/mechanical.py`
- Modify: `codemonkeys/artifacts/schemas/__init__.py`
- Test: `tests/test_mechanical_schemas.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mechanical_schemas.py
from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)


class TestRuffFinding:
    def test_roundtrip(self) -> None:
        finding = RuffFinding(
            file="src/auth.py", line=42, code="F401", message="Unused import"
        )
        data = json.loads(finding.model_dump_json())
        restored = RuffFinding.model_validate(data)
        assert restored == finding

    def test_json_schema_has_descriptions(self) -> None:
        schema = RuffFinding.model_json_schema()
        assert "description" in schema["properties"]["file"]
        assert "description" in schema["properties"]["code"]


class TestPyrightFinding:
    def test_roundtrip(self) -> None:
        finding = PyrightFinding(
            file="src/auth.py",
            line=10,
            severity="error",
            message="Missing return type",
        )
        data = json.loads(finding.model_dump_json())
        restored = PyrightFinding.model_validate(data)
        assert restored == finding

    def test_severity_literal(self) -> None:
        finding = PyrightFinding(
            file="x.py", line=1, severity="warning", message="msg"
        )
        assert finding.severity == "warning"


class TestPytestResult:
    def test_roundtrip(self) -> None:
        result = PytestResult(
            passed=10,
            failed=2,
            errors=0,
            failures=["test_auth::test_login", "test_auth::test_logout"],
        )
        data = json.loads(result.model_dump_json())
        restored = PytestResult.model_validate(data)
        assert restored.passed == 10
        assert len(restored.failures) == 2

    def test_empty_failures(self) -> None:
        result = PytestResult(passed=5, failed=0, errors=0, failures=[])
        assert result.failures == []


class TestCveFinding:
    def test_roundtrip(self) -> None:
        finding = CveFinding(
            package="requests",
            installed_version="2.25.0",
            fixed_version="2.31.0",
            cve_id="CVE-2023-32681",
            severity="high",
            description="Unintended leak of Proxy-Authorization header.",
        )
        data = json.loads(finding.model_dump_json())
        restored = CveFinding.model_validate(data)
        assert restored.cve_id == "CVE-2023-32681"

    def test_fixed_version_nullable(self) -> None:
        finding = CveFinding(
            package="pkg",
            installed_version="1.0",
            fixed_version=None,
            cve_id="CVE-2024-0001",
            severity="critical",
            description="No fix available.",
        )
        assert finding.fixed_version is None


class TestSecretsFinding:
    def test_roundtrip(self) -> None:
        finding = SecretsFinding(
            file="config.py",
            line=5,
            pattern="AWS key",
            snippet="AKIA****XXXX",
        )
        data = json.loads(finding.model_dump_json())
        restored = SecretsFinding.model_validate(data)
        assert restored.pattern == "AWS key"


class TestCoverageMap:
    def test_roundtrip(self) -> None:
        cov = CoverageMap(
            covered=["auth.login", "auth.logout"],
            uncovered=["auth.refresh_token"],
        )
        data = json.loads(cov.model_dump_json())
        restored = CoverageMap.model_validate(data)
        assert len(restored.covered) == 2
        assert len(restored.uncovered) == 1


class TestDeadCodeFinding:
    def test_roundtrip(self) -> None:
        finding = DeadCodeFinding(
            file="src/utils.py", line=88, name="old_helper", kind="function"
        )
        data = json.loads(finding.model_dump_json())
        restored = DeadCodeFinding.model_validate(data)
        assert restored.kind == "function"

    def test_kind_literal(self) -> None:
        finding = DeadCodeFinding(
            file="x.py", line=1, name="OldClass", kind="class"
        )
        assert finding.kind == "class"


class TestMechanicalAuditResult:
    def test_roundtrip(self) -> None:
        result = MechanicalAuditResult(
            ruff=[RuffFinding(file="a.py", line=1, code="F401", message="unused")],
            pyright=[],
            pytest=PytestResult(passed=5, failed=0, errors=0, failures=[]),
            pip_audit=None,
            secrets=[],
            coverage=None,
            dead_code=None,
        )
        data = json.loads(result.model_dump_json())
        restored = MechanicalAuditResult.model_validate(data)
        assert len(restored.ruff) == 1
        assert restored.pip_audit is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mechanical_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'codemonkeys.artifacts.schemas.mechanical'`

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/artifacts/schemas/mechanical.py
"""Schemas for mechanical audit tool results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RuffFinding(BaseModel):
    file: str = Field(description="Relative path to the file")
    line: int = Field(description="Line number of the violation")
    code: str = Field(description="Ruff rule code (e.g. 'F401', 'E501')")
    message: str = Field(description="Human-readable violation message")


class PyrightFinding(BaseModel):
    file: str = Field(description="Relative path to the file")
    line: int = Field(description="Line number of the diagnostic")
    severity: Literal["error", "warning", "information"] = Field(
        description="Pyright diagnostic severity"
    )
    message: str = Field(description="Diagnostic message")


class PytestResult(BaseModel):
    passed: int = Field(description="Number of tests that passed")
    failed: int = Field(description="Number of tests that failed")
    errors: int = Field(description="Number of collection/setup errors")
    failures: list[str] = Field(
        default_factory=list,
        description="Names of failed tests",
    )


class CveFinding(BaseModel):
    package: str = Field(description="Package name with the vulnerability")
    installed_version: str = Field(description="Currently installed version")
    fixed_version: str | None = Field(
        description="Version that fixes the CVE, or null if no fix exists"
    )
    cve_id: str = Field(description="CVE identifier (e.g. 'CVE-2023-32681')")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        description="CVE severity rating"
    )
    description: str = Field(description="Brief description of the vulnerability")


class SecretsFinding(BaseModel):
    file: str = Field(description="Relative path to the file")
    line: int = Field(description="Line number where the secret pattern was found")
    pattern: str = Field(
        description="Which pattern matched (e.g. 'AWS key', 'generic token')"
    )
    snippet: str = Field(description="Masked context around the match")


class CoverageMap(BaseModel):
    covered: list[str] = Field(
        default_factory=list,
        description="Function names with corresponding tests",
    )
    uncovered: list[str] = Field(
        default_factory=list,
        description="Function names lacking test coverage",
    )


class DeadCodeFinding(BaseModel):
    file: str = Field(description="Relative path to the file")
    line: int = Field(description="Line number of the definition")
    name: str = Field(description="Name of the unused function, class, or import")
    kind: Literal["function", "class", "import"] = Field(
        description="What kind of code is unused"
    )


class MechanicalAuditResult(BaseModel):
    ruff: list[RuffFinding] = Field(
        default_factory=list, description="Ruff linter findings"
    )
    pyright: list[PyrightFinding] = Field(
        default_factory=list, description="Pyright type checker findings"
    )
    pytest: PytestResult | None = Field(
        default=None, description="Test suite results"
    )
    pip_audit: list[CveFinding] | None = Field(
        default=None, description="Dependency CVE findings (full repo only)"
    )
    secrets: list[SecretsFinding] = Field(
        default_factory=list, description="Potential secrets in source"
    )
    coverage: CoverageMap | None = Field(
        default=None, description="Function-level test coverage map"
    )
    dead_code: list[DeadCodeFinding] | None = Field(
        default=None, description="Unused code definitions (full repo only)"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mechanical_schemas.py -v`
Expected: All PASS

- [ ] **Step 5: Update schemas __init__.py**

Add to `codemonkeys/artifacts/schemas/__init__.py`:

```python
from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)
```

And add all names to `__all__`.

- [ ] **Step 6: Run full test suite**

Run: `uv run python -m pytest -x -q`
Expected: All PASS

- [ ] **Step 7: Lint and type check**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright .`
Expected: Clean

- [ ] **Step 8: Commit**

```bash
git add codemonkeys/artifacts/schemas/mechanical.py codemonkeys/artifacts/schemas/__init__.py tests/test_mechanical_schemas.py
git commit -m "feat: add mechanical audit result schemas"
```

---

### Task 2: Spec Compliance Schemas

**Files:**
- Create: `codemonkeys/artifacts/schemas/spec_compliance.py`
- Modify: `codemonkeys/artifacts/schemas/__init__.py`
- Test: `tests/test_spec_compliance_schemas.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spec_compliance_schemas.py
from __future__ import annotations

import json

from codemonkeys.artifacts.schemas.spec_compliance import (
    SpecComplianceFinding,
    SpecComplianceFindings,
)


class TestSpecComplianceFinding:
    def test_roundtrip(self) -> None:
        finding = SpecComplianceFinding(
            category="completeness",
            severity="high",
            spec_step="Add login endpoint",
            files=["src/routes/auth.py"],
            title="Login endpoint not implemented",
            description="The spec calls for a POST /login endpoint but no route was created.",
            suggestion="Create the login route in src/routes/auth.py",
        )
        data = json.loads(finding.model_dump_json())
        restored = SpecComplianceFinding.model_validate(data)
        assert restored == finding

    def test_spec_step_nullable(self) -> None:
        finding = SpecComplianceFinding(
            category="scope_creep",
            severity="medium",
            spec_step=None,
            files=["src/analytics.py"],
            title="Unplanned analytics module",
            description="This file was not in the spec.",
            suggestion=None,
        )
        assert finding.spec_step is None

    def test_category_literal(self) -> None:
        for cat in [
            "completeness",
            "scope_creep",
            "contract_compliance",
            "behavioral_fidelity",
            "test_coverage",
        ]:
            finding = SpecComplianceFinding(
                category=cat,
                severity="low",
                spec_step=None,
                files=["x.py"],
                title="test",
                description="test",
                suggestion=None,
            )
            assert finding.category == cat

    def test_json_schema_has_descriptions(self) -> None:
        schema = SpecComplianceFinding.model_json_schema()
        assert "description" in schema["properties"]["category"]
        assert "description" in schema["properties"]["spec_step"]


class TestSpecComplianceFindings:
    def test_roundtrip(self) -> None:
        findings = SpecComplianceFindings(
            spec_title="Add user authentication",
            steps_implemented=3,
            steps_total=5,
            findings=[
                SpecComplianceFinding(
                    category="completeness",
                    severity="high",
                    spec_step="Add refresh token",
                    files=["src/auth.py"],
                    title="Refresh token not implemented",
                    description="Step not done.",
                    suggestion="Implement refresh logic.",
                ),
            ],
        )
        data = json.loads(findings.model_dump_json())
        restored = SpecComplianceFindings.model_validate(data)
        assert restored.steps_implemented == 3
        assert restored.steps_total == 5
        assert len(restored.findings) == 1

    def test_empty_findings(self) -> None:
        findings = SpecComplianceFindings(
            spec_title="Simple feature",
            steps_implemented=2,
            steps_total=2,
            findings=[],
        )
        assert findings.findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_spec_compliance_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# codemonkeys/artifacts/schemas/spec_compliance.py
"""Schemas for spec compliance review findings."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SpecComplianceFinding(BaseModel):
    category: Literal[
        "completeness",
        "scope_creep",
        "contract_compliance",
        "behavioral_fidelity",
        "test_coverage",
    ] = Field(description="Which aspect of spec compliance this finding addresses")
    severity: Literal["high", "medium", "low"] = Field(
        description="Impact severity — high: missing feature, medium: partial, low: minor gap"
    )
    spec_step: str | None = Field(
        description="Which plan step this relates to, or null for general findings"
    )
    files: list[str] = Field(description="Affected file paths")
    title: str = Field(description="Short one-line summary")
    description: str = Field(description="Detailed explanation")
    suggestion: str | None = Field(
        default=None, description="How to resolve the gap"
    )


class SpecComplianceFindings(BaseModel):
    spec_title: str = Field(description="Title of the spec/plan being reviewed")
    steps_implemented: int = Field(description="Number of spec steps that were implemented")
    steps_total: int = Field(description="Total number of spec steps")
    findings: list[SpecComplianceFinding] = Field(
        default_factory=list,
        description="Spec compliance issues found",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_spec_compliance_schemas.py -v`
Expected: All PASS

- [ ] **Step 5: Update schemas __init__.py**

Add to `codemonkeys/artifacts/schemas/__init__.py`:

```python
from codemonkeys.artifacts.schemas.spec_compliance import (
    SpecComplianceFinding,
    SpecComplianceFindings,
)
```

And add both names to `__all__`.

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/artifacts/schemas/spec_compliance.py codemonkeys/artifacts/schemas/__init__.py tests/test_spec_compliance_schemas.py
git commit -m "feat: add spec compliance review schemas"
```

---

### Task 3: New Event Types

**Files:**
- Modify: `codemonkeys/workflows/events.py`
- Test: `tests/test_new_events.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_new_events.py
from __future__ import annotations

from codemonkeys.workflows.events import (
    EventEmitter,
    EventType,
    FindingsSummaryPayload,
    FixProgressPayload,
    MechanicalToolCompletedPayload,
    MechanicalToolStartedPayload,
    TriageReadyPayload,
)


class TestNewEventTypes:
    def test_mechanical_tool_started_exists(self) -> None:
        assert EventType.MECHANICAL_TOOL_STARTED.value == "mechanical_tool_started"

    def test_mechanical_tool_completed_exists(self) -> None:
        assert EventType.MECHANICAL_TOOL_COMPLETED.value == "mechanical_tool_completed"

    def test_findings_summary_exists(self) -> None:
        assert EventType.FINDINGS_SUMMARY.value == "findings_summary"

    def test_triage_ready_exists(self) -> None:
        assert EventType.TRIAGE_READY.value == "triage_ready"

    def test_fix_progress_exists(self) -> None:
        assert EventType.FIX_PROGRESS.value == "fix_progress"


class TestNewPayloads:
    def test_mechanical_tool_started_payload(self) -> None:
        payload = MechanicalToolStartedPayload(tool="ruff", files_count=42)
        assert payload.tool == "ruff"
        assert payload.files_count == 42

    def test_mechanical_tool_completed_payload(self) -> None:
        payload = MechanicalToolCompletedPayload(
            tool="pyright", findings_count=3, duration_ms=1500
        )
        assert payload.tool == "pyright"
        assert payload.findings_count == 3
        assert payload.duration_ms == 1500

    def test_findings_summary_payload(self) -> None:
        payload = FindingsSummaryPayload(
            total=15,
            by_severity={"high": 2, "medium": 5, "low": 8},
            by_category={"quality": 10, "security": 5},
        )
        assert payload.total == 15
        assert payload.by_severity["high"] == 2

    def test_triage_ready_payload(self) -> None:
        payload = TriageReadyPayload(
            findings_count=10,
            fixable_count=7,
        )
        assert payload.findings_count == 10
        assert payload.fixable_count == 7

    def test_fix_progress_payload(self) -> None:
        payload = FixProgressPayload(
            file="src/auth.py", status="completed"
        )
        assert payload.file == "src/auth.py"
        assert payload.status == "completed"


class TestNewEventsEmit:
    def test_emit_mechanical_tool_started(self) -> None:
        emitter = EventEmitter()
        received: list[EventType] = []
        emitter.on(EventType.MECHANICAL_TOOL_STARTED, lambda et, _: received.append(et))
        emitter.emit(
            EventType.MECHANICAL_TOOL_STARTED,
            MechanicalToolStartedPayload(tool="ruff", files_count=5),
        )
        assert len(received) == 1

    def test_emit_fix_progress(self) -> None:
        emitter = EventEmitter()
        received: list[FixProgressPayload] = []
        emitter.on(EventType.FIX_PROGRESS, lambda _, p: received.append(p))
        emitter.emit(
            EventType.FIX_PROGRESS,
            FixProgressPayload(file="a.py", status="started"),
        )
        assert received[0].file == "a.py"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_new_events.py -v`
Expected: FAIL with `ImportError` — new event types don't exist yet

- [ ] **Step 3: Add new event types and payloads to events.py**

Add to the `EventType` enum in `codemonkeys/workflows/events.py`:

```python
    MECHANICAL_TOOL_STARTED = "mechanical_tool_started"
    MECHANICAL_TOOL_COMPLETED = "mechanical_tool_completed"
    FINDINGS_SUMMARY = "findings_summary"
    TRIAGE_READY = "triage_ready"
    FIX_PROGRESS = "fix_progress"
```

Add new payload classes after the existing ones:

```python
class MechanicalToolStartedPayload(BaseModel):
    tool: str = Field(description="Name of the mechanical tool starting")
    files_count: int = Field(description="Number of files being checked")


class MechanicalToolCompletedPayload(BaseModel):
    tool: str = Field(description="Name of the mechanical tool that finished")
    findings_count: int = Field(description="Number of findings produced")
    duration_ms: int = Field(description="Wall-clock time in milliseconds")


class FindingsSummaryPayload(BaseModel):
    total: int = Field(description="Total number of findings across all sources")
    by_severity: dict[str, int] = Field(description="Count per severity level")
    by_category: dict[str, int] = Field(description="Count per category")


class TriageReadyPayload(BaseModel):
    findings_count: int = Field(description="Total findings available for triage")
    fixable_count: int = Field(description="Findings that can be auto-fixed")


class FixProgressPayload(BaseModel):
    file: str = Field(description="File being fixed")
    status: Literal["started", "completed", "failed"] = Field(
        description="Current fix status"
    )
```

Add `Literal` to the typing import at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_new_events.py tests/test_events.py -v`
Expected: All PASS (new + existing event tests)

- [ ] **Step 5: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/workflows/events.py tests/test_new_events.py
git commit -m "feat: add mechanical audit and triage event types"
```

---

### Task 4: New Prompt Templates

**Files:**
- Create: `codemonkeys/core/prompts/hardening_checklist.py`
- Create: `codemonkeys/core/prompts/diff_context.py`
- Modify: `codemonkeys/core/prompts/__init__.py`

- [ ] **Step 1: Create hardening checklist prompt**

```python
# codemonkeys/core/prompts/hardening_checklist.py
"""Post-feature architecture review addition — hardening and integration checks."""

HARDENING_CHECKLIST = """\
## Additional Focus: Hardening & Integration

Beyond the standard design review, also evaluate:

### error_paths

What happens when inputs are invalid, services are down, or operations fail?
Are errors handled at the right layer? Look for bare except blocks that swallow
context, error handlers that silently continue when they should abort, and
missing error handling on I/O boundaries.

### edge_cases

Empty collections, None values, concurrent access, boundary values — are these
handled or will they surface as bugs? Check for assumptions like "this list is
never empty" or "this key always exists" without guards.

### integration_seams

Does this feature interact correctly with existing logging, config, error
handling, and shutdown patterns? New code that ignores established patterns
(e.g., its own logger instead of the project logger, manual config reads
instead of the config system) creates maintenance burden.

### defensive_boundaries

At system edges (user input, file I/O, network, subprocess), is input validated
before being trusted internally? Internal code can trust other internal code,
but data crossing a trust boundary must be checked."""
```

- [ ] **Step 2: Create diff context prompt template**

```python
# codemonkeys/core/prompts/diff_context.py
"""Diff mode context template — injected into file reviewer prompts."""

DIFF_CONTEXT_TEMPLATE = """\
## What Changed (diff context)

These files were modified in this branch. Here are the relevant hunks:

{diff_hunks}

## Call Graph (blast radius)

Functions modified and their direct callers:

{call_graph}

## Focus

Prioritize reviewing the CHANGED code and its interactions. Existing code
that was not touched is only relevant if the changes broke an assumption
it depends on."""
```

- [ ] **Step 3: Update prompts __init__.py**

Add to `codemonkeys/core/prompts/__init__.py`:

```python
from codemonkeys.core.prompts.diff_context import DIFF_CONTEXT_TEMPLATE
from codemonkeys.core.prompts.hardening_checklist import HARDENING_CHECKLIST
```

And add both to `__all__`.

- [ ] **Step 4: Verify imports work**

Run: `uv run python -c "from codemonkeys.core.prompts import HARDENING_CHECKLIST, DIFF_CONTEXT_TEMPLATE; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/core/prompts/hardening_checklist.py codemonkeys/core/prompts/diff_context.py codemonkeys/core/prompts/__init__.py
git commit -m "feat: add hardening checklist and diff context prompt templates"
```

---

### Task 5: Spec Compliance Reviewer Agent

**Files:**
- Create: `codemonkeys/core/agents/spec_compliance_reviewer.py`
- Modify: `codemonkeys/core/agents/__init__.py`
- Test: `tests/test_spec_compliance_reviewer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_spec_compliance_reviewer.py
from __future__ import annotations

from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.core.agents.spec_compliance_reviewer import (
    make_spec_compliance_reviewer,
)


class TestSpecComplianceReviewer:
    def test_returns_agent_definition(self) -> None:
        spec = FeaturePlan(
            title="Add caching",
            description="Add Redis caching to the API layer.",
            steps=[
                PlanStep(description="Add cache module", files=["src/cache.py"]),
                PlanStep(description="Wire into API", files=["src/api.py"]),
            ],
        )
        agent = make_spec_compliance_reviewer(
            spec=spec,
            files=["src/cache.py", "src/api.py"],
            unplanned_files=["src/utils.py"],
        )
        assert agent.model == "opus"
        assert "Read" in agent.tools
        assert "Grep" in agent.tools
        assert agent.permissionMode == "dontAsk"

    def test_prompt_contains_spec_steps(self) -> None:
        spec = FeaturePlan(
            title="Add caching",
            description="Redis caching.",
            steps=[
                PlanStep(description="Add cache module", files=["src/cache.py"]),
            ],
        )
        agent = make_spec_compliance_reviewer(
            spec=spec, files=["src/cache.py"], unplanned_files=[]
        )
        assert "Add cache module" in agent.prompt
        assert "src/cache.py" in agent.prompt

    def test_prompt_contains_unplanned_files(self) -> None:
        spec = FeaturePlan(
            title="Test",
            description="Test.",
            steps=[PlanStep(description="step", files=["a.py"])],
        )
        agent = make_spec_compliance_reviewer(
            spec=spec, files=["a.py", "b.py"], unplanned_files=["b.py"]
        )
        assert "b.py" in agent.prompt
        assert "unplanned" in agent.prompt.lower()

    def test_prompt_contains_checklist_categories(self) -> None:
        spec = FeaturePlan(
            title="T", description="D", steps=[]
        )
        agent = make_spec_compliance_reviewer(
            spec=spec, files=[], unplanned_files=[]
        )
        assert "completeness" in agent.prompt
        assert "scope_creep" in agent.prompt
        assert "contract_compliance" in agent.prompt
        assert "behavioral_fidelity" in agent.prompt
        assert "test_coverage" in agent.prompt


class TestSpecComplianceRegistry:
    def test_registered_in_default_registry(self) -> None:
        from codemonkeys.core.agents import default_registry

        registry = default_registry()
        spec = registry.get("spec-compliance-reviewer")
        assert spec is not None
        assert spec.role.value == "analyzer"
        assert spec.scope == "project"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_spec_compliance_reviewer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the agent factory**

```python
# codemonkeys/core/agents/spec_compliance_reviewer.py
"""Spec compliance reviewer — compares implementation against a plan.

Dispatched during the post-feature review workflow. Receives a FeaturePlan,
the list of implementation files, and any files that changed but were not
in the plan (scope creep signals).
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.artifacts.schemas.plans import FeaturePlan


def make_spec_compliance_reviewer(
    *,
    spec: FeaturePlan,
    files: list[str],
    unplanned_files: list[str],
) -> AgentDefinition:
    """Create a spec compliance reviewer for a completed feature."""
    steps_text = "\n".join(
        f"- **Step {i + 1}:** {step.description}\n"
        f"  Files: {', '.join(f'`{f}`' for f in step.files) or '(none specified)'}"
        for i, step in enumerate(spec.steps)
    )

    files_text = "\n".join(f"- `{f}`" for f in files)

    unplanned_text = (
        "\n".join(f"- `{f}`" for f in unplanned_files)
        if unplanned_files
        else "(none — all changed files are in the spec)"
    )

    return AgentDefinition(
        description=f"Spec compliance review: {spec.title}",
        prompt=f"""\
You review whether an implementation matches its specification. Read the spec,
then read the implementation files, and report any gaps between intent and reality.

## The Spec

**Title:** {spec.title}

**Description:** {spec.description}

### Planned Steps

{steps_text}

## Implementation Files

{files_text}

## Unplanned Files

These files changed but are NOT listed in any spec step:

{unplanned_text}

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping:

```json
{{{{
  "spec_title": "{spec.title}",
  "steps_implemented": <int>,
  "steps_total": {len(spec.steps)},
  "findings": [
    {{{{
      "category": "<completeness|scope_creep|contract_compliance|behavioral_fidelity|test_coverage>",
      "severity": "<high|medium|low>",
      "spec_step": "<step description or null>",
      "files": ["path/to/file.py"],
      "title": "<short description>",
      "description": "<detailed explanation>",
      "suggestion": "<how to fix, or null>"
    }}}}
  ]
}}}}
```

## Checklist

### completeness

Is every spec step implemented? Read the implementation files and verify that
each planned step was actually built. A step is implemented if its described
behavior exists in the code, not just if the listed files exist.

### scope_creep

Do unplanned files contain feature work not in the spec, or are they reasonable
supporting changes (test helpers, type stubs, config updates)? Feature work in
unplanned files means either the spec was incomplete or the implementation grew
beyond scope.

### contract_compliance

Do function signatures, schemas, and interfaces match what the spec described?
If the spec says "takes a list of strings" but the code takes a dict, that is
a contract violation even if the behavior is similar.

### behavioral_fidelity

Does the code do what the spec says, or does it do something subtly different?
Look for edge cases the spec describes that the code does not handle, or behavior
the code implements that the spec does not mention.

### test_coverage

Does each spec step have corresponding tests? Not just that test files exist,
but that the tests actually verify the behavior described in each step.

## Rules

- Only report findings at 80%+ confidence
- `spec_step` is null only for findings not tied to a specific step
- Read the implementation files to verify — do not guess from file names
- If the implementation perfectly matches the spec, return empty findings
- Count `steps_implemented` by reading the code, not by counting files""",
        model="opus",
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
```

- [ ] **Step 4: Register in default_registry**

Add to `codemonkeys/core/agents/__init__.py`:

In the `TYPE_CHECKING` block, add:
```python
    from codemonkeys.core.agents.spec_compliance_reviewer import (
        make_spec_compliance_reviewer as make_spec_compliance_reviewer,
    )
```

In `__all__`, add `"make_spec_compliance_reviewer"`.

In `__getattr__`, add:
```python
    if name == "make_spec_compliance_reviewer":
        from codemonkeys.core.agents.spec_compliance_reviewer import (
            make_spec_compliance_reviewer,
        )
        return make_spec_compliance_reviewer
```

In `default_registry()`, add after the architecture-reviewer registration:
```python
    from codemonkeys.core.agents.spec_compliance_reviewer import (
        make_spec_compliance_reviewer,
    )
    from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings

    registry.register(
        AgentSpec(
            name="spec-compliance-reviewer",
            role=AgentRole.ANALYZER,
            description="Compare implementation against spec/plan for completeness and fidelity",
            scope="project",
            produces=SpecComplianceFindings,
            consumes=FeaturePlan,
            make=make_spec_compliance_reviewer,
        )
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_spec_compliance_reviewer.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/core/agents/spec_compliance_reviewer.py codemonkeys/core/agents/__init__.py tests/test_spec_compliance_reviewer.py
git commit -m "feat: add spec compliance reviewer agent"
```

---

### Task 6: Extend WorkflowContext with Config

**Files:**
- Modify: `codemonkeys/workflows/phases.py`
- Create: `codemonkeys/workflows/compositions.py` (just the config dataclass for now)
- Test: `tests/test_compositions.py` (config tests only)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compositions.py
from __future__ import annotations

from codemonkeys.workflows.compositions import ReviewConfig


class TestReviewConfig:
    def test_full_repo_config(self) -> None:
        config = ReviewConfig(mode="full_repo")
        assert config.audit_tools == {
            "ruff", "pyright", "pytest", "pip_audit", "secrets", "coverage", "dead_code"
        }
        assert config.auto_fix is False
        assert config.max_concurrent == 5
        assert config.base_branch == "main"

    def test_diff_config(self) -> None:
        config = ReviewConfig(mode="diff")
        assert config.audit_tools == {"ruff", "pyright", "pytest", "secrets", "coverage"}
        assert "pip_audit" not in config.audit_tools

    def test_files_config(self) -> None:
        config = ReviewConfig(mode="files", target_files=["a.py", "b.py"])
        assert config.target_files == ["a.py", "b.py"]
        assert config.audit_tools == {"ruff", "pyright", "pytest", "secrets", "coverage"}

    def test_post_feature_config(self) -> None:
        config = ReviewConfig(mode="post_feature", spec_path="docs/plan.md")
        assert config.spec_path == "docs/plan.md"
        assert config.audit_tools == {"ruff", "pyright", "pytest", "secrets", "coverage"}

    def test_auto_fix_override(self) -> None:
        config = ReviewConfig(mode="diff", auto_fix=True)
        assert config.auto_fix is True

    def test_custom_base_branch(self) -> None:
        config = ReviewConfig(mode="diff", base_branch="develop")
        assert config.base_branch == "develop"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_compositions.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add config field to WorkflowContext**

In `codemonkeys/workflows/phases.py`, add to the `WorkflowContext` dataclass:

```python
    config: Any = None
```

This goes after `user_input: Any = None`.

- [ ] **Step 4: Create compositions.py with ReviewConfig**

```python
# codemonkeys/workflows/compositions.py
"""Review workflow compositions — config and workflow builders for each review mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ALL_TOOLS = frozenset(
    {"ruff", "pyright", "pytest", "pip_audit", "secrets", "coverage", "dead_code"}
)
SCOPED_TOOLS = frozenset({"ruff", "pyright", "pytest", "secrets", "coverage"})

_MODE_TOOLS: dict[str, frozenset[str]] = {
    "full_repo": ALL_TOOLS,
    "diff": SCOPED_TOOLS,
    "files": SCOPED_TOOLS,
    "post_feature": SCOPED_TOOLS,
}


@dataclass
class ReviewConfig:
    mode: Literal["full_repo", "diff", "files", "post_feature"]
    target_files: list[str] | None = None
    spec_path: str | None = None
    auto_fix: bool = False
    max_concurrent: int = 5
    base_branch: str = "main"
    audit_tools: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.audit_tools:
            self.audit_tools = set(_MODE_TOOLS[self.mode])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_compositions.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phases.py codemonkeys/workflows/compositions.py tests/test_compositions.py
git commit -m "feat: add ReviewConfig and extend WorkflowContext with config"
```

---

### Task 7: Discovery Phases

**Files:**
- Create: `codemonkeys/workflows/phases/__init__.py`
- Create: `codemonkeys/workflows/phases/discovery.py`
- Test: `tests/test_discovery_phases.py`

- [ ] **Step 1: Write the failing tests**

These tests mock subprocess and filesystem calls to avoid real git/file operations.

```python
# tests/test_discovery_phases.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestDiscoverAllFiles:
    @pytest.mark.asyncio
    async def test_finds_python_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_all_files

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        (tmp_path / "src" / "util.py").write_text("y = 2")
        (tmp_path / "readme.md").write_text("# hi")

        with patch("codemonkeys.workflows.phases.discovery.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0,
                stdout="src/main.py\nsrc/util.py\n",
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="full_repo"),
            )
            result = await discover_all_files(ctx)

        assert "src/main.py" in result["files"]
        assert "src/util.py" in result["files"]
        assert "structural_metadata" in result
        assert "hot_files" in result

    @pytest.mark.asyncio
    async def test_filters_non_python(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_all_files

        with patch("codemonkeys.workflows.phases.discovery.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0,
                stdout="src/main.py\nreadme.md\ndata.json\n",
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="full_repo"),
            )
            result = await discover_all_files(ctx)

        assert "readme.md" not in result["files"]
        assert "data.json" not in result["files"]


class TestDiscoverDiff:
    @pytest.mark.asyncio
    async def test_finds_changed_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_diff

        (tmp_path / "changed.py").write_text("x = 1")

        with patch("codemonkeys.workflows.phases.discovery.subprocess") as mock_sub:
            diff_result = MagicMock(returncode=0, stdout="changed.py\n")
            stat_result = MagicMock(
                returncode=0, stdout=" 1 file changed, 5 insertions(+)\n"
            )
            hunks_result = MagicMock(
                returncode=0, stdout="diff --git a/changed.py b/changed.py\n+x = 1\n"
            )
            mock_sub.run.side_effect = [diff_result, stat_result, hunks_result]

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="diff"),
            )
            result = await discover_diff(ctx)

        assert "changed.py" in result["files"]
        assert "diff_stat" in result
        assert "diff_hunks" in result
        assert "structural_metadata" in result


class TestDiscoverFiles:
    @pytest.mark.asyncio
    async def test_uses_target_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_files

        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["a.py", "b.py"]),
        )
        result = await discover_files(ctx)

        assert result["files"] == ["a.py", "b.py"]
        assert "structural_metadata" in result

    @pytest.mark.asyncio
    async def test_filters_missing_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_files

        (tmp_path / "a.py").write_text("x = 1")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["a.py", "missing.py"]),
        )
        result = await discover_files(ctx)

        assert "a.py" in result["files"]
        assert "missing.py" not in result["files"]


class TestDiscoverFromSpec:
    @pytest.mark.asyncio
    async def test_reads_spec_and_finds_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phases.discovery import discover_from_spec

        spec = FeaturePlan(
            title="Add caching",
            description="Redis caching.",
            steps=[PlanStep(description="Add cache", files=["src/cache.py"])],
        )
        spec_path = tmp_path / "plan.json"
        spec_path.write_text(spec.model_dump_json())
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "cache.py").write_text("x = 1")

        with patch("codemonkeys.workflows.phases.discovery.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="src/cache.py\nsrc/extra.py\n"
            )

            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(
                    mode="post_feature", spec_path=str(spec_path)
                ),
            )
            result = await discover_from_spec(ctx)

        assert "src/cache.py" in result["files"]
        assert result["spec"].title == "Add caching"
        assert "src/cache.py" in result["spec_files"]
        assert "src/extra.py" in result["unplanned_files"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_discovery_phases.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the phases package __init__.py**

```python
# codemonkeys/workflows/phases/__init__.py
"""Reusable phase functions for review workflows."""

from __future__ import annotations

from codemonkeys.workflows.phases.discovery import (
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
)

__all__ = [
    "discover_all_files",
    "discover_diff",
    "discover_files",
    "discover_from_spec",
]
```

Note: This will be extended in later tasks as more phase modules are added. The existing `phases.py` at `codemonkeys/workflows/phases.py` (defines `Phase`, `PhaseType`, `Workflow`, `WorkflowContext`) stays unchanged. The new directory is `codemonkeys/workflows/phase_library/` to avoid the naming collision.

```python
# codemonkeys/workflows/phase_library/__init__.py
"""Reusable phase functions for review workflows."""

from __future__ import annotations

from codemonkeys.workflows.phase_library.discovery import (
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
)

__all__ = [
    "discover_all_files",
    "discover_diff",
    "discover_files",
    "discover_from_spec",
]
```

Update the test imports accordingly — use `codemonkeys.workflows.phase_library.discovery` instead of `codemonkeys.workflows.phases.discovery`. Import `WorkflowContext` from `codemonkeys.workflows.phases`.

- [ ] **Step 4: Write discovery.py**

```python
# codemonkeys/workflows/phase_library/discovery.py
"""Discovery phase functions — file collection and metadata for each review mode."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.plans import FeaturePlan
from codemonkeys.core.analysis import analyze_files, format_analysis
from codemonkeys.workflows.phases import WorkflowContext

VENDORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", ".tox", "dist", ".eggs", "node_modules", ".git"}
)


async def discover_all_files(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)
    config = ctx.config

    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        files = [
            f
            for f in result.stdout.strip().splitlines()
            if f.endswith(".py")
            and not any(part in Path(f).parts for part in VENDORED_DIRS)
        ]
    else:
        files = [
            str(p.relative_to(cwd))
            for p in cwd.rglob("*.py")
            if not any(part in p.parts for part in VENDORED_DIRS)
        ]

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)

    hot_files = _compute_hot_files(files, analyses, cwd)

    return {
        "files": files,
        "structural_metadata": structural_metadata,
        "hot_files": hot_files,
    }


async def discover_diff(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)
    config = ctx.config
    base = config.base_branch

    name_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    files = [
        f
        for f in (name_result.stdout.strip().splitlines() if name_result.returncode == 0 else [])
        if f.endswith(".py")
    ]

    stat_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--stat"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_stat = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

    hunks_result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--"] + files,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_hunks = hunks_result.stdout if hunks_result.returncode == 0 else ""

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)

    call_graph = _build_call_graph(files, analyses, cwd)

    return {
        "files": files,
        "diff_stat": diff_stat,
        "diff_hunks": diff_hunks,
        "structural_metadata": structural_metadata,
        "call_graph": call_graph,
    }


async def discover_files(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)
    config = ctx.config
    target = config.target_files or []

    files = [f for f in target if (cwd / f).exists()]

    analyses = analyze_files(files, root=cwd)
    structural_metadata = format_analysis(analyses)

    return {
        "files": files,
        "structural_metadata": structural_metadata,
    }


async def discover_from_spec(ctx: WorkflowContext) -> dict[str, Any]:
    cwd = Path(ctx.cwd)
    config = ctx.config

    spec_path = Path(config.spec_path)
    if not spec_path.is_absolute():
        spec_path = cwd / spec_path
    spec = FeaturePlan.model_validate_json(spec_path.read_text())

    spec_files: set[str] = set()
    for step in spec.steps:
        spec_files.update(step.files)

    diff_result = subprocess.run(
        ["git", "diff", f"{config.base_branch}...HEAD", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    diff_files = set(
        f
        for f in (diff_result.stdout.strip().splitlines() if diff_result.returncode == 0 else [])
        if f.endswith(".py")
    )

    all_files = sorted(spec_files | diff_files)
    unplanned = sorted(diff_files - spec_files)

    analyses = analyze_files(all_files, root=cwd)
    structural_metadata = format_analysis(analyses)

    return {
        "files": all_files,
        "spec": spec,
        "structural_metadata": structural_metadata,
        "spec_files": sorted(spec_files),
        "unplanned_files": unplanned,
    }


def _compute_hot_files(
    files: list[str],
    analyses: list,
    cwd: Path,
) -> list[dict[str, Any]]:
    """Cross-reference git churn with import fanout to find high-risk files."""
    result = subprocess.run(
        ["git", "log", "--format=", "--name-only", "--since=6 months ago"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    churn: dict[str, int] = {}
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                churn[line] = churn.get(line, 0) + 1

    import_counts: dict[str, int] = {}
    for analysis in analyses:
        for imp in analysis.imports:
            module = imp.get("module", "") or ""
            for f in files:
                stem = f.replace("/", ".").removesuffix(".py")
                if module.startswith(stem) or stem.endswith(module):
                    import_counts[f] = import_counts.get(f, 0) + 1

    hot = []
    for f in files:
        c = churn.get(f, 0)
        i = import_counts.get(f, 0)
        if c > 0 or i > 0:
            hot.append({"file": f, "churn": c, "importers": i, "score": c * (i + 1)})

    hot.sort(key=lambda h: h["score"], reverse=True)
    return hot[:20]


def _build_call_graph(
    files: list[str],
    analyses: list,
    cwd: Path,
) -> str:
    """Build a simple call graph showing functions defined in changed files and who imports them."""
    defined: dict[str, list[str]] = {}
    for analysis in analyses:
        names = [fn.name for fn in analysis.functions]
        names.extend(cls.name for cls in analysis.classes)
        if names:
            defined[analysis.file] = names

    if not defined:
        return "(no functions found in changed files)"

    lines = []
    for file, names in defined.items():
        lines.append(f"### `{file}` defines: {', '.join(names)}")

    return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_discovery_phases.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phase_library/ tests/test_discovery_phases.py
git commit -m "feat: add discovery phase functions for all review modes"
```

---

### Task 8: Mechanical Audit Phase

**Files:**
- Create: `codemonkeys/workflows/phase_library/mechanical.py`
- Modify: `codemonkeys/workflows/phase_library/__init__.py`
- Test: `tests/test_mechanical_phase.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mechanical_phase.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestMechanicalAudit:
    @pytest.mark.asyncio
    async def test_runs_ruff(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        ruff_json = '[{"filename": "a.py", "location": {"row": 1}, "code": "F401", "message": "unused"}]'

        with patch("codemonkeys.workflows.phase_library.mechanical.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=1, stdout=ruff_json, stderr=""
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"ruff"}
            result = await mechanical_audit(ctx)

        assert len(result["mechanical"].ruff) == 1
        assert result["mechanical"].ruff[0].code == "F401"

    @pytest.mark.asyncio
    async def test_skips_disabled_tools(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        with patch("codemonkeys.workflows.phase_library.mechanical.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"ruff"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].pip_audit is None
        assert result["mechanical"].dead_code is None

    @pytest.mark.asyncio
    async def test_runs_pytest(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        with patch("codemonkeys.workflows.phase_library.mechanical.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0,
                stdout="5 passed\n",
                stderr="",
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"pytest"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].pytest is not None


class TestSecretsScanner:
    @pytest.mark.asyncio
    async def test_detects_aws_key(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _scan_secrets

        target = tmp_path / "config.py"
        target.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        findings = _scan_secrets(["config.py"], tmp_path)
        assert len(findings) >= 1
        assert findings[0].pattern == "AWS access key"

    @pytest.mark.asyncio
    async def test_no_false_positive_on_normal_code(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _scan_secrets

        target = tmp_path / "clean.py"
        target.write_text("x = 42\nname = 'hello'\n")

        findings = _scan_secrets(["clean.py"], tmp_path)
        assert findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mechanical_phase.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write mechanical.py**

```python
# codemonkeys/workflows/phase_library/mechanical.py
"""Mechanical audit phase — subprocess tools for deterministic code analysis."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS secret key", re.compile(r"""(?:aws_secret|secret_key|SECRET_KEY)\s*=\s*['"][A-Za-z0-9/+=]{40}['"]""")),
    ("Generic API key", re.compile(r"""(?:api[_-]?key|apikey)\s*=\s*['"][A-Za-z0-9]{20,}['"]""", re.IGNORECASE)),
    ("Generic secret", re.compile(r"""(?:secret|password|passwd|token)\s*=\s*['"][^'"]{8,}['"]""", re.IGNORECASE)),
    ("Private key header", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
]


async def mechanical_audit(ctx: WorkflowContext) -> dict[str, MechanicalAuditResult]:
    cwd = Path(ctx.cwd)
    config = ctx.config
    tools = config.audit_tools
    files: list[str] = ctx.phase_results.get("discover", {}).get("files", [])

    result = MechanicalAuditResult()

    if "ruff" in tools:
        result.ruff = _run_ruff(files, cwd)
    if "pyright" in tools:
        result.pyright = _run_pyright(files, cwd)
    if "pytest" in tools:
        result.pytest = _run_pytest(cwd)
    if "pip_audit" in tools:
        result.pip_audit = _run_pip_audit(cwd)
    if "secrets" in tools:
        result.secrets = _scan_secrets(files, cwd)
    if "coverage" in tools:
        result.coverage = _compute_coverage(files, cwd)
    if "dead_code" in tools:
        result.dead_code = _find_dead_code(files, cwd)

    return {"mechanical": result}


def _run_ruff(files: list[str], cwd: Path) -> list[RuffFinding]:
    if not files:
        return []
    r = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "--output-format=json"] + files,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for item in data:
        findings.append(
            RuffFinding(
                file=item.get("filename", ""),
                line=item.get("location", {}).get("row", 0),
                code=item.get("code", ""),
                message=item.get("message", ""),
            )
        )
    return findings


def _run_pyright(files: list[str], cwd: Path) -> list[PyrightFinding]:
    if not files:
        return []
    r = subprocess.run(
        [PYTHON, "-m", "pyright", "--outputjson"] + files,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for diag in data.get("generalDiagnostics", []):
        findings.append(
            PyrightFinding(
                file=diag.get("file", ""),
                line=diag.get("range", {}).get("start", {}).get("line", 0),
                severity=diag.get("severity", "information"),
                message=diag.get("message", ""),
            )
        )
    return findings


def _run_pytest(cwd: Path) -> PytestResult:
    r = subprocess.run(
        [PYTHON, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    passed = failed = errors = 0
    failures: list[str] = []
    for line in r.stdout.splitlines():
        match = re.match(r"(\d+) passed", line)
        if match:
            passed = int(match.group(1))
        match = re.match(r"(\d+) failed", line)
        if match:
            failed = int(match.group(1))
        match = re.match(r"(\d+) error", line)
        if match:
            errors = int(match.group(1))
        if line.startswith("FAILED"):
            failures.append(line.removeprefix("FAILED ").strip())
    return PytestResult(passed=passed, failed=failed, errors=errors, failures=failures)


def _run_pip_audit(cwd: Path) -> list[CveFinding]:
    r = subprocess.run(
        [PYTHON, "-m", "pip_audit", "--format=json"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for item in data:
        for vuln in item.get("vulns", []):
            findings.append(
                CveFinding(
                    package=item.get("name", ""),
                    installed_version=item.get("version", ""),
                    fixed_version=vuln.get("fix_versions", [None])[0]
                    if vuln.get("fix_versions")
                    else None,
                    cve_id=vuln.get("id", ""),
                    severity=vuln.get("severity", "medium").lower(),
                    description=vuln.get("description", ""),
                )
            )
    return findings


def _scan_secrets(files: list[str], cwd: Path) -> list[SecretsFinding]:
    findings = []
    for file_path in files:
        full = cwd / file_path
        if not full.exists():
            continue
        try:
            lines = full.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            for pattern_name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    masked = line[:20] + "****" + line[-10:] if len(line) > 34 else "****"
                    findings.append(
                        SecretsFinding(
                            file=file_path,
                            line=i,
                            pattern=pattern_name,
                            snippet=masked,
                        )
                    )
                    break
    return findings


def _compute_coverage(files: list[str], cwd: Path) -> CoverageMap:
    from codemonkeys.core.analysis import analyze_files

    analyses = analyze_files(files, root=cwd)
    covered = []
    uncovered = []

    for analysis in analyses:
        for fn in analysis.functions:
            test_name = f"test_{analysis.file}".replace("/", "_").replace(".py", "")
            test_exists = any(
                (cwd / "tests" / f"{test_name}.py").exists()
                for test_name in [
                    f"test_{Path(analysis.file).stem}",
                    f"test_{fn.name}",
                ]
            )
            if test_exists:
                covered.append(f"{analysis.file}::{fn.name}")
            else:
                uncovered.append(f"{analysis.file}::{fn.name}")

    return CoverageMap(covered=covered, uncovered=uncovered)


def _find_dead_code(files: list[str], cwd: Path) -> list[DeadCodeFinding]:
    from codemonkeys.core.analysis import analyze_files

    analyses = analyze_files(files, root=cwd)
    findings = []

    for analysis in analyses:
        for fn in analysis.functions:
            if fn.name.startswith("_"):
                continue
            r = subprocess.run(
                ["grep", "-r", "--include=*.py", "-l", fn.name, "."],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            referencing_files = [
                f.strip().removeprefix("./")
                for f in r.stdout.strip().splitlines()
                if f.strip()
            ]
            referencing_files = [f for f in referencing_files if f != analysis.file]
            if not referencing_files:
                findings.append(
                    DeadCodeFinding(
                        file=analysis.file,
                        line=1,
                        name=fn.name,
                        kind="function",
                    )
                )

        for cls in analysis.classes:
            r = subprocess.run(
                ["grep", "-r", "--include=*.py", "-l", cls.name, "."],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            referencing_files = [
                f.strip().removeprefix("./")
                for f in r.stdout.strip().splitlines()
                if f.strip()
            ]
            referencing_files = [f for f in referencing_files if f != analysis.file]
            if not referencing_files:
                findings.append(
                    DeadCodeFinding(
                        file=analysis.file,
                        line=1,
                        name=cls.name,
                        kind="class",
                    )
                )

    return findings
```

- [ ] **Step 4: Update phase_library/__init__.py**

Add to `codemonkeys/workflows/phase_library/__init__.py`:

```python
from codemonkeys.workflows.phase_library.mechanical import mechanical_audit
```

And add `"mechanical_audit"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mechanical_phase.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phase_library/mechanical.py codemonkeys/workflows/phase_library/__init__.py tests/test_mechanical_phase.py
git commit -m "feat: add mechanical audit phase with subprocess tool runners"
```

---

### Task 9: Agent Phases (file_review, architecture_review, doc_review, spec_compliance_review)

**Files:**
- Create: `codemonkeys/workflows/phase_library/review.py`
- Modify: `codemonkeys/workflows/phase_library/__init__.py`
- Test: `tests/test_review_phases.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_phases.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


def _make_ctx(
    tmp_path: Path,
    mode: str = "full_repo",
    phase_results: dict | None = None,
    **kwargs,
) -> WorkflowContext:
    return WorkflowContext(
        cwd=str(tmp_path),
        run_id="test/run1",
        config=ReviewConfig(mode=mode, **kwargs),
        phase_results=phase_results or {},
    )


class TestFileReview:
    @pytest.mark.asyncio
    async def test_dispatches_reviewer_per_batch(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import file_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FileFindings(
                file="a.py", summary="test", findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={"discover": {"files": ["a.py", "b.py"], "structural_metadata": ""}},
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await file_review(ctx)

        assert "file_findings" in result
        assert mock_runner.run_agent.call_count >= 1


class TestArchitectureReview:
    @pytest.mark.asyncio
    async def test_dispatches_architecture_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import architecture_review
        from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=ArchitectureFindings(
                files_reviewed=["a.py"], findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "discover": {
                    "files": ["a.py"],
                    "structural_metadata": "### a.py\n  x = 1",
                },
                "file_review": {
                    "file_findings": [
                        FileFindings(file="a.py", summary="test module", findings=[])
                    ]
                },
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await architecture_review(ctx)

        assert "architecture_findings" in result
        mock_runner.run_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_feature_includes_hardening(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import architecture_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output={"files_reviewed": [], "findings": []}
        )

        ctx = _make_ctx(
            tmp_path,
            mode="post_feature",
            spec_path="plan.json",
            phase_results={
                "discover": {"files": ["a.py"], "structural_metadata": ""},
                "file_review": {"file_findings": []},
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            await architecture_review(ctx)

        call_args = mock_runner.run_agent.call_args
        prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("prompt", "")
        assert "hardening" in prompt.lower() or "error_paths" in prompt.lower()


class TestDocReview:
    @pytest.mark.asyncio
    async def test_dispatches_both_reviewers(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import doc_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FileFindings(
                file="README.md", summary="readme", findings=[]
            ).model_dump()
        )

        ctx = _make_ctx(tmp_path, phase_results={"discover": {"files": ["a.py"]}})

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await doc_review(ctx)

        assert "doc_findings" in result
        assert mock_runner.run_agent.call_count == 2


class TestSpecComplianceReview:
    @pytest.mark.asyncio
    async def test_dispatches_spec_reviewer(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.review import spec_compliance_review

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output={
                "spec_title": "Test",
                "steps_implemented": 1,
                "steps_total": 1,
                "findings": [],
            }
        )

        spec = FeaturePlan(
            title="Test",
            description="Test.",
            steps=[PlanStep(description="step", files=["a.py"])],
        )
        ctx = _make_ctx(
            tmp_path,
            mode="post_feature",
            spec_path="plan.json",
            phase_results={
                "discover": {
                    "files": ["a.py"],
                    "spec": spec,
                    "unplanned_files": [],
                }
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.review.AgentRunner",
            return_value=mock_runner,
        ):
            result = await spec_compliance_review(ctx)

        assert "spec_findings" in result
        mock_runner.run_agent.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_review_phases.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write review.py**

```python
# codemonkeys/workflows/phase_library/review.py
"""Agent phases — dispatch reviewer agents and collect structured findings."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings
from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings
from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer
from codemonkeys.core.agents.spec_compliance_reviewer import make_spec_compliance_reviewer
from codemonkeys.core.prompts import DIFF_CONTEXT_TEMPLATE, HARDENING_CHECKLIST
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext


async def file_review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    files: list[str] = ctx.phase_results["discover"]["files"]
    config = ctx.config
    runner = AgentRunner(cwd=ctx.cwd)

    is_test = lambda f: "test" in f.split("/")[-1]
    batches: list[tuple[list[str], str]] = []
    test_batch: list[str] = []
    prod_batch: list[str] = []

    for f in files:
        if is_test(f):
            test_batch.append(f)
            if len(test_batch) == 3:
                batches.append((test_batch, "haiku"))
                test_batch = []
        else:
            prod_batch.append(f)
            if len(prod_batch) == 3:
                batches.append((prod_batch, "sonnet"))
                prod_batch = []

    if test_batch:
        batches.append((test_batch, "haiku"))
    if prod_batch:
        batches.append((prod_batch, "sonnet"))

    all_findings: list[FileFindings] = []

    for batch_files, model in batches:
        agent = make_python_file_reviewer(batch_files, model=model)

        prompt = f"Review: {', '.join(batch_files)}"
        if config.mode == "diff":
            diff_hunks = ctx.phase_results["discover"].get("diff_hunks", "")
            call_graph = ctx.phase_results["discover"].get("call_graph", "")
            prompt = DIFF_CONTEXT_TEMPLATE.format(
                diff_hunks=diff_hunks, call_graph=call_graph
            ) + f"\n\nReview: {', '.join(batch_files)}"

        output_format = {
            "type": "json_schema",
            "schema": FileFindings.model_json_schema(),
        }
        raw = await runner.run_agent(agent, prompt, output_format=output_format)

        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            findings = FileFindings.model_validate(structured)
        else:
            try:
                findings = FileFindings.model_validate_json(raw)
            except Exception:
                findings = FileFindings(
                    file=batch_files[0],
                    summary="Could not parse output",
                    findings=[],
                )
        all_findings.append(findings)

    return {"file_findings": all_findings}


async def architecture_review(ctx: WorkflowContext) -> dict[str, ArchitectureFindings]:
    files: list[str] = ctx.phase_results["discover"]["files"]
    structural_metadata: str = ctx.phase_results["discover"]["structural_metadata"]
    file_findings: list[FileFindings] = ctx.phase_results.get("file_review", {}).get(
        "file_findings", []
    )
    config = ctx.config

    file_summaries = [{"file": f.file, "summary": f.summary} for f in file_findings]

    agent = make_architecture_reviewer(
        files=files,
        file_summaries=file_summaries,
        structural_metadata=structural_metadata,
    )

    prompt = "Review the codebase for cross-file design issues."
    if config.mode == "post_feature":
        prompt += f"\n\n{HARDENING_CHECKLIST}"
    elif config.mode == "full_repo":
        hot_files = ctx.phase_results["discover"].get("hot_files", [])
        if hot_files:
            hot_text = "\n".join(
                f"- `{h['file']}` (churn: {h['churn']}, importers: {h['importers']})"
                for h in hot_files[:10]
            )
            prompt += f"\n\n## Hot Files (high churn + high fanout)\n\n{hot_text}"
    elif config.mode == "diff":
        prompt += "\n\nFocus on module boundaries touched by the diff."

    runner = AgentRunner(cwd=ctx.cwd)
    output_format = {
        "type": "json_schema",
        "schema": ArchitectureFindings.model_json_schema(),
    }
    raw = await runner.run_agent(agent, prompt, output_format=output_format)

    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        findings = ArchitectureFindings.model_validate(structured)
    else:
        try:
            findings = ArchitectureFindings.model_validate_json(raw)
        except Exception:
            findings = ArchitectureFindings(files_reviewed=files, findings=[])

    return {"architecture_findings": findings}


async def doc_review(ctx: WorkflowContext) -> dict[str, list[FileFindings]]:
    runner = AgentRunner(cwd=ctx.cwd)
    output_format = {
        "type": "json_schema",
        "schema": FileFindings.model_json_schema(),
    }
    all_findings: list[FileFindings] = []

    readme_agent = make_readme_reviewer()
    raw = await runner.run_agent(readme_agent, "Review README.md", output_format=output_format)
    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        all_findings.append(FileFindings.model_validate(structured))
    else:
        try:
            all_findings.append(FileFindings.model_validate_json(raw))
        except Exception:
            all_findings.append(
                FileFindings(file="README.md", summary="Could not parse", findings=[])
            )

    changelog_agent = make_changelog_reviewer()
    raw = await runner.run_agent(
        changelog_agent, "Review CHANGELOG.md", output_format=output_format
    )
    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        all_findings.append(FileFindings.model_validate(structured))
    else:
        try:
            all_findings.append(FileFindings.model_validate_json(raw))
        except Exception:
            all_findings.append(
                FileFindings(
                    file="CHANGELOG.md", summary="Could not parse", findings=[]
                )
            )

    return {"doc_findings": all_findings}


async def spec_compliance_review(
    ctx: WorkflowContext,
) -> dict[str, SpecComplianceFindings]:
    discover = ctx.phase_results["discover"]
    spec = discover["spec"]
    files = discover["files"]
    unplanned = discover.get("unplanned_files", [])

    agent = make_spec_compliance_reviewer(
        spec=spec, files=files, unplanned_files=unplanned
    )
    runner = AgentRunner(cwd=ctx.cwd)
    output_format = {
        "type": "json_schema",
        "schema": SpecComplianceFindings.model_json_schema(),
    }
    raw = await runner.run_agent(
        agent,
        f"Review implementation against spec: {spec.title}",
        output_format=output_format,
    )

    structured = getattr(runner.last_result, "structured_output", None)
    if structured:
        if isinstance(structured, str):
            structured = json.loads(structured)
        findings = SpecComplianceFindings.model_validate(structured)
    else:
        try:
            findings = SpecComplianceFindings.model_validate_json(raw)
        except Exception:
            findings = SpecComplianceFindings(
                spec_title=spec.title,
                steps_implemented=0,
                steps_total=len(spec.steps),
                findings=[],
            )

    return {"spec_findings": findings}
```

- [ ] **Step 4: Update phase_library/__init__.py**

Add:
```python
from codemonkeys.workflows.phase_library.review import (
    architecture_review,
    doc_review,
    file_review,
    spec_compliance_review,
)
```

Add all four to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_review_phases.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phase_library/review.py codemonkeys/workflows/phase_library/__init__.py tests/test_review_phases.py
git commit -m "feat: add agent review phases (file, architecture, doc, spec compliance)"
```

---

### Task 10: Action Phases (triage, fix, verify, report)

**Files:**
- Create: `codemonkeys/workflows/phase_library/action.py`
- Modify: `codemonkeys/workflows/phase_library/__init__.py`
- Test: `tests/test_action_phases.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_action_phases.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


def _make_finding(file: str = "a.py", severity: str = "medium") -> Finding:
    return Finding(
        file=file,
        line=10,
        severity=severity,
        category="quality",
        subcategory="naming",
        title="Bad name",
        description="Variable has a bad name.",
        suggestion="Rename it.",
    )


def _make_ctx(tmp_path: Path, phase_results: dict, **kwargs) -> WorkflowContext:
    return WorkflowContext(
        cwd=str(tmp_path),
        run_id="test/run1",
        config=ReviewConfig(mode="full_repo", **kwargs),
        phase_results=phase_results,
    )


class TestTriage:
    @pytest.mark.asyncio
    async def test_auto_fix_selects_medium_and_above(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        ctx = _make_ctx(
            tmp_path,
            auto_fix=True,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[
                                _make_finding(severity="high"),
                                _make_finding(severity="medium"),
                                _make_finding(severity="low"),
                                _make_finding(severity="info"),
                            ],
                        )
                    ]
                },
            },
        )
        result = await triage(ctx)
        requests = result["fix_requests"]
        assert len(requests) == 1
        assert len(requests[0].findings) == 2

    @pytest.mark.asyncio
    async def test_collects_from_multiple_sources(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import triage

        ctx = _make_ctx(
            tmp_path,
            auto_fix=True,
            phase_results={
                "file_review": {
                    "file_findings": [
                        FileFindings(
                            file="a.py",
                            summary="test",
                            findings=[_make_finding(file="a.py")],
                        )
                    ]
                },
                "doc_review": {
                    "doc_findings": [
                        FileFindings(
                            file="README.md",
                            summary="readme",
                            findings=[_make_finding(file="README.md")],
                        )
                    ]
                },
            },
        )
        result = await triage(ctx)
        files_in_requests = {r.file for r in result["fix_requests"]}
        assert "a.py" in files_in_requests
        assert "README.md" in files_in_requests


class TestFix:
    @pytest.mark.asyncio
    async def test_dispatches_fixer_per_file(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import fix

        mock_runner = MagicMock()
        mock_runner.run_agent = AsyncMock(return_value="{}")
        mock_runner.last_result = MagicMock(
            structured_output=FixResult(
                file="a.py", fixed=["fixed naming"], skipped=[]
            ).model_dump()
        )

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "triage": {
                    "fix_requests": [
                        FixRequest(file="a.py", findings=[_make_finding()]),
                        FixRequest(file="b.py", findings=[_make_finding(file="b.py")]),
                    ]
                }
            },
        )

        with patch(
            "codemonkeys.workflows.phase_library.action.AgentRunner",
            return_value=mock_runner,
        ):
            result = await fix(ctx)

        assert len(result["fix_results"]) == 2
        assert mock_runner.run_agent.call_count == 2


class TestVerify:
    @pytest.mark.asyncio
    async def test_returns_verification_result(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import verify

        with patch("codemonkeys.workflows.phase_library.action.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ctx = _make_ctx(tmp_path, phase_results={})
            result = await verify(ctx)

        assert "verification" in result
        assert result["verification"].tests_passed is True
        assert result["verification"].lint_passed is True


class TestReport:
    @pytest.mark.asyncio
    async def test_summarizes_results(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.action import report

        ctx = _make_ctx(
            tmp_path,
            phase_results={
                "fix": {
                    "fix_results": [
                        FixResult(file="a.py", fixed=["fix1", "fix2"], skipped=["skip1"])
                    ]
                },
                "verify": {
                    "verification": VerificationResult(
                        tests_passed=True,
                        lint_passed=True,
                        typecheck_passed=True,
                        errors=[],
                    )
                },
            },
        )
        result = await report(ctx)
        assert result["summary"]["fixed"] == 2
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["tests_passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_action_phases.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write action.py**

```python
# codemonkeys/workflows/phase_library/action.py
"""Action phases — triage, fix, verify, report (shared tail for all workflows)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.runner import AgentRunner
from codemonkeys.workflows.phases import WorkflowContext

PYTHON = sys.executable


async def triage(ctx: WorkflowContext) -> dict[str, list[FixRequest]]:
    config = ctx.config
    all_findings: dict[str, list[Finding]] = {}

    file_findings: list[FileFindings] = (
        ctx.phase_results.get("file_review", {}).get("file_findings", [])
    )
    for ff in file_findings:
        for f in ff.findings:
            all_findings.setdefault(f.file, []).append(f)

    doc_findings: list[FileFindings] = (
        ctx.phase_results.get("doc_review", {}).get("doc_findings", [])
    )
    for ff in doc_findings:
        for f in ff.findings:
            all_findings.setdefault(f.file, []).append(f)

    arch_findings = ctx.phase_results.get("architecture_review", {}).get(
        "architecture_findings"
    )
    if arch_findings:
        for af in arch_findings.findings:
            finding = Finding(
                file=af.files[0] if af.files else "",
                line=None,
                severity=af.severity,
                category="quality",
                subcategory=af.subcategory,
                title=af.title,
                description=af.description,
                suggestion=af.suggestion,
                source="architecture-reviewer",
            )
            all_findings.setdefault(finding.file, []).append(finding)

    if config.auto_fix:
        fix_requests = []
        for file, findings in all_findings.items():
            fixable = [f for f in findings if f.severity in ("high", "medium")]
            if fixable:
                fix_requests.append(FixRequest(file=file, findings=fixable))
        return {"fix_requests": fix_requests}

    if ctx.user_input is not None:
        return {"fix_requests": ctx.user_input}

    fix_requests = []
    for file, findings in all_findings.items():
        if findings:
            fix_requests.append(FixRequest(file=file, findings=findings))
    return {"fix_requests": fix_requests}


async def fix(ctx: WorkflowContext) -> dict[str, list[FixResult]]:
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
        await runner.run_agent(
            agent, f"Fix findings in {request.file}", output_format=output_format
        )
        structured = getattr(runner.last_result, "structured_output", None)
        if structured:
            if isinstance(structured, str):
                structured = json.loads(structured)
            result = FixResult.model_validate(structured)
        else:
            result = FixResult(
                file=request.file, fixed=[], skipped=["Could not parse agent output"]
            )
        results.append(result)

    return {"fix_results": results}


async def verify(ctx: WorkflowContext) -> dict[str, VerificationResult]:
    cwd = Path(ctx.cwd)

    tests = subprocess.run(
        [PYTHON, "-m", "pytest", "-x", "-q", "--tb=line", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    lint = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    typecheck = subprocess.run(
        [PYTHON, "-m", "pyright", "."],
        capture_output=True,
        text=True,
        cwd=cwd,
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


async def report(ctx: WorkflowContext) -> dict[str, Any]:
    fix_results: list[FixResult] = ctx.phase_results.get("fix", {}).get(
        "fix_results", []
    )
    verification: VerificationResult | None = ctx.phase_results.get("verify", {}).get(
        "verification"
    )

    fixed_count = sum(len(r.fixed) for r in fix_results)
    skipped_count = sum(len(r.skipped) for r in fix_results)

    return {
        "summary": {
            "fixed": fixed_count,
            "skipped": skipped_count,
            "tests_passed": verification.tests_passed if verification else None,
            "lint_passed": verification.lint_passed if verification else None,
            "typecheck_passed": verification.typecheck_passed if verification else None,
        }
    }
```

- [ ] **Step 4: Update phase_library/__init__.py**

Add:
```python
from codemonkeys.workflows.phase_library.action import fix, report, triage, verify
```

Add all four to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_action_phases.py -v`
Expected: All PASS

- [ ] **Step 6: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 7: Commit**

```bash
git add codemonkeys/workflows/phase_library/action.py codemonkeys/workflows/phase_library/__init__.py tests/test_action_phases.py
git commit -m "feat: add action phases (triage, fix, verify, report)"
```

---

### Task 11: Workflow Compositions

**Files:**
- Modify: `codemonkeys/workflows/compositions.py`
- Modify: `tests/test_compositions.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_compositions.py`:

```python
from codemonkeys.workflows.compositions import (
    ReviewConfig,
    make_diff_workflow,
    make_files_workflow,
    make_full_repo_workflow,
    make_post_feature_workflow,
)
from codemonkeys.workflows.phases import PhaseType


class TestFullRepoWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_full_repo_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "architecture_review",
            "doc_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_triage_is_gate(self) -> None:
        workflow = make_full_repo_workflow()
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.GATE

    def test_auto_fix_triage_is_automated(self) -> None:
        workflow = make_full_repo_workflow(auto_fix=True)
        triage = next(p for p in workflow.phases if p.name == "triage")
        assert triage.phase_type == PhaseType.AUTOMATED


class TestDiffWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_diff_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "architecture_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_no_doc_review(self) -> None:
        workflow = make_diff_workflow()
        names = [p.name for p in workflow.phases]
        assert "doc_review" not in names


class TestFilesWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_files_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "file_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_no_architecture_or_doc_review(self) -> None:
        workflow = make_files_workflow()
        names = [p.name for p in workflow.phases]
        assert "architecture_review" not in names
        assert "doc_review" not in names


class TestPostFeatureWorkflow:
    def test_has_expected_phases(self) -> None:
        workflow = make_post_feature_workflow()
        names = [p.name for p in workflow.phases]
        assert names == [
            "discover",
            "mechanical_audit",
            "spec_compliance_review",
            "file_review",
            "architecture_review",
            "doc_review",
            "triage",
            "fix",
            "verify",
            "report",
        ]

    def test_has_spec_compliance_before_file_review(self) -> None:
        workflow = make_post_feature_workflow()
        names = [p.name for p in workflow.phases]
        spec_idx = names.index("spec_compliance_review")
        file_idx = names.index("file_review")
        assert spec_idx < file_idx
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_compositions.py::TestFullRepoWorkflow -v`
Expected: FAIL with `ImportError` — workflow builders don't exist yet

- [ ] **Step 3: Add workflow builders to compositions.py**

Add to `codemonkeys/workflows/compositions.py`:

```python
from codemonkeys.workflows.phase_library import (
    architecture_review,
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
    doc_review,
    file_review,
    fix,
    mechanical_audit,
    report,
    spec_compliance_review,
    triage,
    verify,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow


def make_full_repo_workflow(*, auto_fix: bool = False) -> Workflow:
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="full_repo_review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_all_files),
            Phase(name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=mechanical_audit),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review),
            Phase(name="architecture_review", phase_type=PhaseType.AUTOMATED, execute=architecture_review),
            Phase(name="doc_review", phase_type=PhaseType.AUTOMATED, execute=doc_review),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_diff_workflow(*, auto_fix: bool = False) -> Workflow:
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="diff_review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_diff),
            Phase(name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=mechanical_audit),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review),
            Phase(name="architecture_review", phase_type=PhaseType.AUTOMATED, execute=architecture_review),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_files_workflow(*, auto_fix: bool = False) -> Workflow:
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="files_review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_files),
            Phase(name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=mechanical_audit),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )


def make_post_feature_workflow(*, auto_fix: bool = False) -> Workflow:
    triage_type = PhaseType.AUTOMATED if auto_fix else PhaseType.GATE
    return Workflow(
        name="post_feature_review",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=discover_from_spec),
            Phase(name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=mechanical_audit),
            Phase(name="spec_compliance_review", phase_type=PhaseType.AUTOMATED, execute=spec_compliance_review),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=file_review),
            Phase(name="architecture_review", phase_type=PhaseType.AUTOMATED, execute=architecture_review),
            Phase(name="doc_review", phase_type=PhaseType.AUTOMATED, execute=doc_review),
            Phase(name="triage", phase_type=triage_type, execute=triage),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=fix),
            Phase(name="verify", phase_type=PhaseType.AUTOMATED, execute=verify),
            Phase(name="report", phase_type=PhaseType.AUTOMATED, execute=report),
        ],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_compositions.py -v`
Expected: All PASS

- [ ] **Step 5: Lint, type check, full tests**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -x -q`
Expected: All clean

- [ ] **Step 6: Commit**

```bash
git add codemonkeys/workflows/compositions.py tests/test_compositions.py
git commit -m "feat: add four review workflow compositions"
```

---

### Task 12: Integration Smoke Test

**Files:**
- Test: `tests/test_workflow_integration.py`

Verify that each workflow can be instantiated, configured, and the engine runs through the phase sequence (with mocked agents). This catches import errors, signature mismatches, and phase wiring bugs.

- [ ] **Step 1: Write integration tests**

```python
# tests/test_workflow_integration.py
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.workflows.compositions import (
    ReviewConfig,
    make_diff_workflow,
    make_files_workflow,
    make_full_repo_workflow,
    make_post_feature_workflow,
)
from codemonkeys.workflows.engine import WorkflowEngine
from codemonkeys.workflows.events import EventEmitter, EventType
from codemonkeys.workflows.phases import WorkflowContext


def _mock_runner():
    runner = MagicMock()
    runner.run_agent = AsyncMock(return_value="{}")
    runner.last_result = MagicMock(
        structured_output=FileFindings(
            file="a.py", summary="test", findings=[]
        ).model_dump()
    )
    return runner


class TestFilesWorkflowIntegration:
    @pytest.mark.asyncio
    async def test_full_run_with_mocked_agents(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")

        workflow = make_files_workflow(auto_fix=True)
        config = ReviewConfig(mode="files", target_files=["a.py"], auto_fix=True)
        ctx = WorkflowContext(
            cwd=str(tmp_path), run_id="test/run1", config=config
        )
        emitter = EventEmitter()
        events: list[EventType] = []
        emitter.on_any(lambda et, _: events.append(et))
        engine = WorkflowEngine(emitter)

        with (
            patch(
                "codemonkeys.workflows.phase_library.review.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch(
                "codemonkeys.workflows.phase_library.action.AgentRunner",
                return_value=_mock_runner(),
            ),
            patch("codemonkeys.workflows.phase_library.mechanical.subprocess") as mock_sub,
            patch("codemonkeys.workflows.phase_library.action.subprocess") as mock_sub2,
        ):
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_sub2.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            await engine.run(workflow, ctx)

        assert EventType.WORKFLOW_COMPLETED in events
        assert "summary" in ctx.phase_results.get("report", {})
```

- [ ] **Step 2: Run integration test**

Run: `uv run python -m pytest tests/test_workflow_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run pyright . && uv run python -m pytest -v`
Expected: All clean, all passing

- [ ] **Step 4: Commit**

```bash
git add tests/test_workflow_integration.py
git commit -m "test: add workflow integration smoke test"
```
