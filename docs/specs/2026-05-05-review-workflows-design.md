# Review Workflows Design Spec

Four review modes implemented as composable phase-based workflows. Each mode follows a senior engineer's methodology — mechanical tools gather context, agents apply judgment, findings are triaged and fixed.

## Review Modes

| Mode | Trigger | Scope | Intent Source |
|------|---------|-------|---------------|
| Full Repo | `--repo` | All Python files | Inferred from codebase |
| Diff | `--diff` | Changed files on branch | Commit messages + diff |
| Files | `--files a.py b.py` | User-specified files | User context |
| Post-Feature | `--post-feature --spec path` | Spec files + git diff | Plan/spec file |

## Architecture: Phase Library + Composition

Approach B — a library of reusable async phase functions, composed into per-mode workflow definitions. Each phase has the signature:

```python
async def phase_name(ctx: WorkflowContext) -> dict
```

Phases read from `ctx.phase_results` (prior phases) and return a dict stored under their name. The `WorkflowEngine` runs phases in order, pausing at GATE phases for user input.

### Workflow Compositions

```python
FullRepoWorkflow = [
    discover_all_files,       # all .py files, AST analysis, hot file scores
    mechanical_audit,         # ruff, pyright, pytest, pip-audit, secrets, coverage, dead code
    file_review,              # per-file quality/security (batched, parallel)
    architecture_review,      # cross-file design review
    doc_review,               # readme + changelog (parallel)
    triage,                   # GATE — present findings, NLP selection
    fix,                      # code fixer per file (parallel)
    verify,                   # pytest, ruff, pyright
    report,                   # summary
]

DiffWorkflow = [
    discover_diff,            # changed files + callee resolution via AST
    mechanical_audit,         # ruff, pyright, pytest, secrets, coverage
    file_review,              # per-file review with diff hunks + call graph context
    architecture_review,      # scoped to changed module boundaries
    triage,                   # GATE
    fix,
    verify,
    report,
]

FilesWorkflow = [
    discover_files,           # user-specified files, AST analysis
    mechanical_audit,         # ruff, pyright, pytest, secrets, coverage
    file_review,              # per-file quality/security
    triage,                   # GATE
    fix,
    verify,
    report,
]

PostFeatureWorkflow = [
    discover_from_spec,       # files from plan + git diff, detect unplanned files
    mechanical_audit,         # ruff, pyright, pytest, secrets, coverage
    spec_compliance_review,   # spec vs implementation comparison
    file_review,              # per-file quality/security
    architecture_review,      # with hardening + integration checklist
    doc_review,               # did new features get documented?
    triage,                   # GATE
    fix,
    verify,
    report,
]
```

## Phase Library

### Discovery Phases

#### `discover_all_files`

Full repo mode. Finds all Python files via `git ls-files '*.py'`, filters vendored/generated. Runs AST analysis on all files. Computes hot file scores by cross-referencing git churn (`git log --format='' --name-only | sort | uniq -c`) with import graph fanout.

**Returns:** `{"files", "structural_metadata", "hot_files"}`

#### `discover_diff`

Diff mode. Gets changed files via `git diff main...HEAD --name-only --diff-filter=d`. Resolves callees of changed functions one level deep via AST — expands the review scope to catch blast radius. Computes diff stat and extracts diff hunks per file.

**Returns:** `{"files", "diff_stat", "diff_hunks", "structural_metadata", "call_graph"}`

#### `discover_files`

Files mode. Takes user-specified file paths from `ctx.config["target_files"]`. Validates they exist. Runs AST analysis.

**Returns:** `{"files", "structural_metadata"}`

#### `discover_from_spec`

Post-feature mode. Reads the spec/plan file from `ctx.config["spec_path"]`, parses it as `FeaturePlan`. Extracts file paths from plan steps. Unions with `git diff main...HEAD` to catch unplanned changes (scope creep signal).

**Returns:** `{"files", "spec", "structural_metadata", "spec_files", "unplanned_files"}`

### Mechanical Audit Phase

#### `mechanical_audit`

Parameterized by `ctx.config["audit_tools"]` — a set of tool names to run.

```python
ALL_TOOLS = {"ruff", "pyright", "pytest", "pip_audit", "secrets", "coverage", "dead_code"}
SCOPED_TOOLS = {"ruff", "pyright", "pytest", "secrets", "coverage"}
```

Each tool is an async subprocess call. Results collected into typed schemas:

| Tool | Command | Output Schema |
|------|---------|---------------|
| `ruff` | `ruff check --output-format json {files}` | `list[RuffFinding]` |
| `pyright` | `pyright --outputjson {files}` | `list[PyrightFinding]` |
| `pytest` | `pytest --tb=short -q` | `PytestResult` |
| `pip_audit` | `pip-audit --format json` | `list[CveFinding]` |
| `secrets` | Regex grep for API keys, tokens, passwords | `list[SecretsFinding]` |
| `coverage` | Cross-ref function defs vs test files | `CoverageMap` |
| `dead_code` | AST def sites with zero grep hits | `list[DeadCodeFinding]` |

**Returns:** `{"mechanical": {"ruff": [...], "pyright": [...], "pytest": {...}, ...}}`

### Agent Phases

#### `file_review`

Batches files (up to 3 per agent). Routes: test files to haiku, production files to sonnet. Dispatches reviewers in parallel (configurable concurrency, default 5).

**Mode-aware prompt enrichment:**
- **Diff mode:** User prompt includes diff hunks + call graph for the batched files, plus instruction to prioritize changed code.
- **All other modes:** Standard quality/security review.

**Returns:** `{"file_findings": list[FileFindings]}`

#### `architecture_review`

Dispatches the architecture reviewer with structural metadata + per-file finding summaries.

**Mode-aware prompt enrichment:**
- **Post-feature mode:** Appends hardening/integration checklist (error_paths, edge_cases, integration_seams, defensive_boundaries).
- **Full repo mode:** Includes hot file data as priority signal.
- **Diff mode:** Scoped to changed module boundaries only.

**Returns:** `{"architecture_findings": ArchitectureFindings}`

#### `doc_review`

Dispatches `readme_reviewer` and `changelog_reviewer` in parallel.

**Returns:** `{"doc_findings": list[FileFindings]}`

#### `spec_compliance_review`

Dispatches the new `spec_compliance_reviewer` agent with:
- The `FeaturePlan` from discovery
- Implementation file list
- Unplanned files list (scope creep signal)

**Returns:** `{"spec_findings": SpecComplianceFindings}`

### Action Phases (Shared Tail)

#### `triage`

Collects ALL findings from prior phases — mechanical findings (converted to common Finding format), file findings, architecture findings, doc findings, spec compliance findings. Deduplicates (ruff finding that matches a file reviewer finding). Sorts by severity x blast radius.

**Phase type:** GATE (interactive) or AUTOMATED (auto-fix mode via `ctx.config["auto_fix"]`).

- **Interactive:** Emits `TRIAGE_READY` event with findings. UI presents them. Waits for user NLP input. A lightweight haiku call parses the user's natural language selection (e.g., "fix all the security issues and the naming stuff in runner.py") into `FixRequest` objects by matching against the findings list.
- **Auto-fix:** Converts all fixable findings (severity >= medium) to `FixRequest` objects.

**Returns:** `{"fix_requests": list[FixRequest]}`

#### `fix`

Dispatches `python_code_fixer` per file in parallel. Each fixer receives the findings for its file.

**Returns:** `{"fix_results": list[FixResult]}`

#### `verify`

Runs pytest, ruff check, pyright as subprocess calls. Confirms fixes didn't break anything.

**Returns:** `{"verification": VerificationResult}`

#### `report`

Summarizes the run: total findings by category/severity, what was fixed, what was skipped, verification pass/fail. Emits `WORKFLOW_COMPLETED` event with summary payload.

**Returns:** Summary dict.

## New Agent: spec_compliance_reviewer

### Factory

```python
def make_spec_compliance_reviewer(
    spec: FeaturePlan,
    files: list[str],
    unplanned_files: list[str],
) -> AgentDefinition
```

### Configuration

- **Model:** Opus (reasoning about intent vs implementation)
- **Tools:** Read, Grep (read-only)
- **Permission mode:** dontAsk
- **Scope:** Project

### Prompt Checklist

```
- completeness: Is every spec step implemented? Any steps skipped or partial?
- scope_creep: Do unplanned files contain feature work not in the spec,
  or reasonable supporting changes?
- contract_compliance: Do function signatures, schemas, and interfaces
  match what the spec described?
- behavioral_fidelity: Does the code do what the spec says, or something
  subtly different?
- test_coverage: Does each spec step have corresponding tests?
```

### Output Schema

```python
class SpecComplianceFinding(BaseModel):
    category: Literal[
        "completeness", "scope_creep", "contract_compliance",
        "behavioral_fidelity", "test_coverage"
    ]
    severity: Literal["high", "medium", "low"]
    spec_step: str | None       # which plan step this relates to
    files: list[str]            # affected files
    title: str
    description: str
    suggestion: str | None

class SpecComplianceFindings(BaseModel):
    spec_title: str
    steps_implemented: int
    steps_total: int
    findings: list[SpecComplianceFinding] = []
```

### Registry Entry

```python
AgentSpec(
    name="spec-compliance-reviewer",
    role=AgentRole.ANALYZER,
    description="Compares implementation against spec/plan for completeness and fidelity",
    scope="project",
    produces=SpecComplianceFindings,
    consumes=FeaturePlan,
    make=make_spec_compliance_reviewer,
)
```

## New Schemas: Mechanical Audit

```python
class RuffFinding(BaseModel):
    file: str
    line: int
    code: str               # e.g. "E501", "F401"
    message: str

class PyrightFinding(BaseModel):
    file: str
    line: int
    severity: Literal["error", "warning", "information"]
    message: str

class PytestResult(BaseModel):
    passed: int
    failed: int
    errors: int
    failures: list[str]     # test names that failed

class CveFinding(BaseModel):
    package: str
    installed_version: str
    fixed_version: str | None
    cve_id: str
    severity: Literal["critical", "high", "medium", "low"]
    description: str

class SecretsFinding(BaseModel):
    file: str
    line: int
    pattern: str            # which pattern matched (e.g. "AWS key", "generic token")
    snippet: str            # masked context

class CoverageMap(BaseModel):
    covered: list[str]      # functions with corresponding test
    uncovered: list[str]    # functions lacking tests

class DeadCodeFinding(BaseModel):
    file: str
    line: int
    name: str               # function/class name
    kind: Literal["function", "class", "import"]
```

## Prompt Additions

### Architecture Reviewer — Hardening Checklist (Post-Feature Mode)

Appended to user prompt when dispatched from `PostFeatureWorkflow`:

```
## Additional Focus: Hardening & Integration

- error_paths: What happens when inputs are invalid, services are down,
  or operations fail? Are errors handled at the right layer?
- edge_cases: Empty collections, None values, concurrent access,
  boundary values — handled or will they surface as bugs?
- integration_seams: Does this feature interact correctly with existing
  logging, config, error handling, and shutdown patterns?
- defensive_boundaries: At system edges (user input, file I/O, network),
  is input validated before being trusted internally?
```

Findings use the existing `ArchitectureFinding` schema with `subcategory` set to the checklist item name.

### File Reviewer — Diff Context (Diff Mode)

Prepended to user prompt when dispatched from `DiffWorkflow`:

```
## What Changed (diff context)

These files were modified in this branch. Here are the relevant hunks:
{diff hunks for batched files}

## Call Graph (blast radius)

Functions modified and their direct callers:
{call_graph entries}

## Focus

Prioritize reviewing the CHANGED code and its interactions. Existing code
is only relevant if the changes broke an assumption it depends on.
```

## Event System Additions

New event types added to the existing `EventType` enum:

| Event | Payload | Purpose |
|-------|---------|---------|
| `MECHANICAL_TOOL_STARTED` | `{tool: str, files_count: int}` | "Running pip-audit..." |
| `MECHANICAL_TOOL_COMPLETED` | `{tool: str, findings_count: int, duration_ms: int}` | Tool result inline |
| `FINDINGS_SUMMARY` | `{total: int, by_severity: dict, by_category: dict}` | Pre-triage overview |
| `TRIAGE_READY` | `{findings: list, display_format: str}` | UI renders findings for selection |
| `FIX_PROGRESS` | `{file: str, status: "started"\|"completed"\|"failed"}` | Per-file fix status |

Existing events unchanged: `PHASE_STARTED`, `PHASE_COMPLETED`, `AGENT_STARTED`, `AGENT_PROGRESS`, `AGENT_COMPLETED`, `FINDING_ADDED`, `WAITING_FOR_USER`, `WORKFLOW_COMPLETED`, `WORKFLOW_ERROR`.

## UI Contract

Workflows never import UI code. The frontend implements an event handler:

```python
async def handle_event(event_type: EventType, payload: dict) -> None: ...
```

- **CLI:** Rich console tables, progress bars, panel displays
- **TUI:** Textual widgets subscribed to event stream
- **Web:** Events serialized as JSON over websocket

The triage gate is resolved by the frontend calling `engine.resolve_gate(user_input)` with the user's NLP selection text. The workflow's triage phase parses this into fix requests.

## Sandbox & Safety

All agents execute within `restrict(cwd)` — confined to the project working directory. Reviewer agents (file_reviewer, architecture_reviewer, spec_compliance_reviewer, doc reviewers) only receive Read/Grep tools. The fixer agent gets Edit/Write/Bash but remains sandboxed.

Mechanical tools run as subprocess calls from the workflow engine (not from agents). They inherit the engine's working directory.

## File Structure

```
codemonkeys/
  core/
    agents/
      spec_compliance_reviewer.py   # NEW — factory + prompt
      ...existing agents unchanged
    prompts/
      hardening_checklist.py        # NEW — post-feature architecture prompt addition
      diff_context.py               # NEW — template for diff mode file reviewer
      ...existing prompts unchanged
  artifacts/schemas/
    mechanical.py                   # NEW — RuffFinding, CveFinding, etc.
    spec_compliance.py              # NEW — SpecComplianceFindings
    ...existing schemas unchanged
  workflows/
    phases/                         # NEW directory
      __init__.py
      discovery.py                  # discover_all_files, discover_diff, discover_files, discover_from_spec
      mechanical.py                 # mechanical_audit + individual tool runners
      review.py                     # file_review, architecture_review, doc_review, spec_compliance_review
      action.py                     # triage, fix, verify, report
    compositions.py                 # NEW — FullRepoWorkflow, DiffWorkflow, FilesWorkflow, PostFeatureWorkflow
    engine.py                       # existing, unchanged
    events.py                       # existing, extended with new event types
    phases.py                       # existing, unchanged (WorkflowContext, Phase, Workflow)
```

## Configuration

Workflow config passed via `ctx.config`:

```python
@dataclass
class ReviewConfig:
    mode: Literal["full_repo", "diff", "files", "post_feature"]
    audit_tools: set[str]           # which mechanical tools to run
    target_files: list[str] | None  # files mode only
    spec_path: str | None           # post-feature mode only
    auto_fix: bool = False          # skip triage gate, fix all >= medium
    max_concurrent: int = 5         # parallel agent limit
    base_branch: str = "main"       # for diff calculation
```
