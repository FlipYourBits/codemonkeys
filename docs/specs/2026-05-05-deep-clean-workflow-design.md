# Deep Clean Workflow Design Spec

A new `--deep-clean` workflow that takes an unfamiliar or debt-laden codebase and transforms it into clean, well-structured code through automated stabilization and incremental structural refactoring.

## Intent

The existing `--repo` workflow reviews and spot-fixes individual findings. Deep clean goes further: it stabilizes the project (ensures it can build, has test coverage, has healthy deps), then systematically restructures the code through opinionated refactoring steps — each gated by user approval.

Target use case: "I just inherited this repo" or "this codebase has years of accumulated debt."

## CLI Interface

```
uv run python -m codemonkeys.run_review --deep-clean
```

Separate from `--repo`. Both can coexist — run `--repo` after `--deep-clean` to catch remaining quality issues.

## New Agents

### python_characterization_tester

Writes tests that lock current behavior for uncovered source files.

| Property | Value |
|----------|-------|
| Model | Sonnet |
| Tools | Read, Write, Bash (pytest only) |
| Input | Source file, direct imports, coverage data (uncovered lines) |
| Output | Test file(s) that pass against current source |
| Constraint | Tests MUST pass. If a test fails, fix the test — never the source. |

**System prompt includes:** Python testing guidelines, coverage-driven test generation strategy.

**Batching:** Same as file_review — up to 3 files per agent, parallel with semaphore (max_concurrent from config).

**Registry entry:**
```python
AgentSpec(
    name="python-characterization-tester",
    role=AgentRole.EXECUTOR,
    description="Write characterization tests for uncovered source files",
    scope="file",
    produces=CharTestResult,
    consumes=CoverageResult,
    make=make_python_characterization_tester,
)
```

### python_structural_refactorer

Executes scoped structural changes: break cycles, split modules, enforce layering, extract shared code, delete dead code, normalize naming.

| Property | Value |
|----------|-------|
| Model | Sonnet |
| Tools | Read, Write, Edit, Bash (pytest scoped, ruff) |
| Input | Affected files (2-5 max), specific problem description, fix strategy from StructuralReport |
| Output | StructuralRefactorResult — files changed, what was done, tests pass/fail |
| Constraint | Only touch files listed in input. Run scoped pytest after changes. Max 2 fix cycles. |

**Single agent definition, different prompts per refactor step.** The prompt tells it what structural problem to solve; the agent's core capability (read files, restructure, verify) stays the same.

**Registry entry:**
```python
AgentSpec(
    name="python-structural-refactorer",
    role=AgentRole.EXECUTOR,
    description="Execute scoped structural refactoring (cycles, layering, splitting, naming)",
    scope="file",
    produces=StructuralRefactorResult,
    consumes=StructuralReport,
    make=make_python_structural_refactorer,
)
```

## New Mechanical Phases

### build_check

Try importing all top-level Python modules in the project. Catches missing deps, syntax errors, circular imports at load time.

```python
async def build_check(ctx: WorkflowContext) -> dict[str, BuildCheckResult]
```

**Implementation:** For each top-level module (directories with `__init__.py` or standalone `.py` files at project root), run `python -c "import module_name"`. Collect pass/fail per module.

**Output schema:**
```python
@dataclass
class BuildCheckResult:
    loadable: list[str]       # modules that imported successfully
    broken: list[str]         # modules that failed
    errors: dict[str, str]    # module -> error message
```

**Failure behavior:** If any modules are broken, present findings to user. This is informational — the workflow continues (broken modules will be flagged but not block characterization test generation for working modules).

### dependency_health

Check for unused deps, missing lock file, outdated packages.

```python
async def dependency_health(ctx: WorkflowContext) -> dict[str, DependencyHealthResult]
```

**Implementation:**
1. Parse all imports across source files (AST — already have this infrastructure)
2. Compare against installed packages to find unused deps
3. Check for existence of `uv.lock` / `poetry.lock` / pinned `requirements.txt`
4. Run `pip list --outdated --format=json` for outdated package report

**Output schema:**
```python
@dataclass
class DependencyHealthResult:
    unused: list[str]                   # installed but never imported
    missing_lockfile: bool
    outdated: list[OutdatedPackage]     # name, current, latest
```

### structural_analysis

Build the full structural picture that all refactoring steps consume. Computed once, re-run (cheap) after refactoring completes.

```python
async def structural_analysis(ctx: WorkflowContext) -> dict[str, StructuralReport]
```

**Implementation (all AST/subprocess, zero LLM):**
1. Build full import graph (module → modules it imports)
2. Detect circular dependencies (Tarjan's SCC algorithm)
3. Compute file complexity metrics (lines, function count, class count, max function length)
4. Identify layer violations (configurable: e.g., "utils should not import from workflows")
5. Find naming inconsistencies (mixed conventions within the project)
6. Build test→source mapping from pytest-cov data (which tests hit which source lines)
7. Compute hot-file scores (git churn × import fanout) for prioritization

**Output schema:**
```python
@dataclass
class StructuralReport:
    import_graph: dict[str, list[str]]
    circular_deps: list[list[str]]          # each cycle as ordered list
    file_metrics: dict[str, FileMetrics]    # file -> complexity stats
    layer_violations: list[LayerViolation]
    naming_issues: list[NamingIssue]
    test_source_map: dict[str, list[str]]   # test_file -> source_files it covers
    hot_files: list[HotFile]                # ordered by risk score
```

### coverage_measurement

Run pytest with coverage and parse the JSON report.

```python
async def coverage_measurement(ctx: WorkflowContext) -> dict[str, CoverageResult]
```

**Implementation:** `pytest --cov --cov-report=json -q` → parse `coverage.json`.

**Output schema:**
```python
@dataclass
class CoverageResult:
    overall_percent: float
    per_file: dict[str, FileCoverage]  # file -> lines covered, lines missed, percent
    uncovered_files: list[str]         # files with <40% coverage
```

## Workflow Composition

```python
def make_deep_clean_workflow() -> Workflow:
    return Workflow(
        name="deep_clean",
        phases=[
            # --- Stabilize ---
            Phase(name="build_check", phase_type=AUTOMATED, execute=build_check),
            Phase(name="dependency_health", phase_type=AUTOMATED, execute=dependency_health),
            Phase(name="coverage", phase_type=AUTOMATED, execute=coverage_measurement),
            Phase(name="structural_analysis", phase_type=AUTOMATED, execute=structural_analysis),
            Phase(name="characterization_tests", phase_type=AUTOMATED, execute=characterization_tests),

            # --- Refactor (each step is a GATE) ---
            Phase(name="refactor_circular_deps", phase_type=GATE, execute=refactor_step),
            Phase(name="refactor_layering", phase_type=GATE, execute=refactor_step),
            Phase(name="refactor_god_modules", phase_type=GATE, execute=refactor_step),
            Phase(name="refactor_extract_shared", phase_type=GATE, execute=refactor_step),
            Phase(name="refactor_dead_code", phase_type=GATE, execute=refactor_step),
            Phase(name="refactor_naming", phase_type=GATE, execute=refactor_step),

            # --- Finalize ---
            Phase(name="rescan_structure", phase_type=AUTOMATED, execute=structural_analysis),
            Phase(name="update_readme", phase_type=AUTOMATED, execute=update_readme),
            Phase(name="final_verify", phase_type=AUTOMATED, execute=final_verify),
            Phase(name="report", phase_type=AUTOMATED, execute=report),
        ],
    )
```

## Integration with Refactored Architecture

### AgentRunner Usage

All agent phases instantiate `AgentRunner` with the context's emitter and log_dir:

```python
runner = AgentRunner(cwd=ctx.cwd, emitter=ctx.emitter, log_dir=ctx.log_dir)
result: RunResult = await runner.run_agent(agent, prompt, output_format=output_format)
```

`RunResult` provides:
- `result.text` — raw LLM output
- `result.structured` — parsed JSON-schema output (dict or None)
- `result.usage` — token counts
- `result.cost` — USD cost
- `result.duration_ms` — elapsed time

Phase functions never parse raw SDK messages — AgentRunner handles all message processing, event emission, and debug logging internally.

### WorkflowEngine Gate Pattern

Refactor steps use the `GATE` phase type. The engine:
1. Emits `WAITING_FOR_USER` event with phase details
2. Creates an `asyncio.Future` and blocks
3. CLI calls `engine.resolve_gate(user_input)` to unblock

The refactor step's execute function receives `ctx.user_input` (set by the gate resolver) to know whether the user approved or skipped.

### Event Emission

New phases emit events via `ctx.emitter` following existing patterns:
- `MECHANICAL_TOOL_STARTED` / `MECHANICAL_TOOL_COMPLETED` for subprocess tools
- `AGENT_STARTED` / `AGENT_PROGRESS` / `AGENT_COMPLETED` via AgentRunner (automatic)
- Phase lifecycle (`PHASE_STARTED` / `PHASE_COMPLETED`) handled by WorkflowEngine

### CLI Wiring

```python
# run_review.py — _pick_workflow()
if config.mode == "deep_clean":
    return make_deep_clean_workflow()

# run_review.py — _resolve_mode()
if args.deep_clean:
    return "deep_clean"
```

The thin CLI layer handles only arg parsing and gate resolution. All execution logic lives in phase functions + AgentRunner.

## Refactor Step Execution Detail

Each `refactor_*` phase uses the same `python_structural_refactorer` agent with a step-specific prompt. The GATE type means the workflow pauses before execution to show the user what it found and what it proposes to change.

**Gate presentation (per step):**
```
Step 3: Break God Modules
────────────────────────
Found 2 files exceeding complexity threshold:

  1. core/runner.py (487 lines, 12 functions, 3 classes)
     Proposal: Extract progress display into core/progress.py

  2. workflows/engine.py (392 lines, 9 functions)
     Proposal: Extract event emission into workflows/events.py

Approve? [Y/n/skip]
```

**On approve:**
1. Dispatch `python_structural_refactorer` with only affected files
2. Agent reads files, makes changes, runs scoped pytest (tests from test→source map)
3. If tests fail: agent fixes (max 2 cycles)
4. Return result, advance to next step

**On skip:** Advance to next step without changes.

**Empty steps:** If structural_analysis found no issues for a step (e.g., no circular deps), the step is auto-skipped with a message: "No circular dependencies detected — skipping."

## Context Budget Per Agent Call

| Phase | Files agent reads | Context source |
|-------|-------------------|----------------|
| characterization_tests | 1 source file + direct imports (1-3 files) | Coverage data from coverage_measurement |
| refactor_* | 2-5 affected files only | Problem identified by structural_analysis |
| update_readme | 1 file (README.md) | Updated StructuralReport (JSON) |

No agent ever reads the full repo. The mechanical phases (zero LLM cost) do the broad analysis; agents get surgically scoped inputs.

## Scoped Test Execution

When a refactoring agent needs to verify its changes, it runs only the tests that cover the files it modified. The test→source mapping (from coverage_measurement, stored in StructuralReport) provides this:

```
Agent modified: core/runner.py, core/progress.py
test→source map says: tests/test_runner.py covers core/runner.py
Characterization test: tests/test_characterization_runner.py covers core/runner.py
→ Run: pytest tests/test_runner.py tests/test_characterization_runner.py -x -q
```

For newly created files (extracted modules), there's no existing test coverage. The agent creates the file and ensures existing tests that imported the original module still pass.

## Characterization Test Phase Detail

```python
async def characterization_tests(ctx: WorkflowContext) -> dict[str, CharTestResult]
```

**Input:** Files from `coverage_measurement.uncovered_files` (those with <40% line coverage).

**Batching:** Up to 3 files per agent call, parallel with semaphore.

**Per-batch agent input:**
- Source files (the uncovered ones)
- Their direct imports (from structural_analysis.import_graph — so the agent understands deps without reading them)
- Coverage data: which specific lines are uncovered

**Agent writes:** Test files following project convention (`tests/test_<stem>.py`).

**Validation:** Agent runs the tests it wrote. They must all pass (characterizing current behavior). If any fail, agent fixes the test.

**Output:**
```python
@dataclass
class CharTestResult:
    tests_written: list[str]       # paths to new test files
    files_covered: list[str]       # source files now covered
    coverage_after: float | None   # re-measured if feasible
```

## Final Verify Phase

Runs the full mechanical suite one last time after all refactoring:

1. `pytest` (full suite — including characterization tests)
2. `ruff check .`
3. `pyright .`
4. Import check (all top-level modules still loadable)

If any fail, results are displayed in the final report with instructions for manual resolution.

## ReviewConfig Changes

```python
@dataclass
class ReviewConfig:
    mode: Literal["full_repo", "diff", "files", "post_feature", "deep_clean"]
    # ... existing fields ...
    coverage_threshold: float = 40.0  # files below this get characterization tests
    layer_rules: dict[str, list[str]] | None = None  # optional: "module" -> ["cannot import from"]
```

`_MODE_TOOLS` addition:
```python
_MODE_TOOLS["deep_clean"] = ALL_TOOLS  # all mechanical tools enabled
```

## New Schemas

All new output schemas live in `codemonkeys/artifacts/schemas/` as Pydantic models (matching existing pattern):

- `structural.py` — StructuralReport, FileMetrics, LayerViolation, NamingIssue, HotFile
- `coverage.py` — CoverageResult, FileCoverage
- `health.py` — BuildCheckResult, DependencyHealthResult, OutdatedPackage
- `refactor.py` — StructuralRefactorResult, CharTestResult

## Agent Registry Updates

Both new agents are registered in `default_registry()` in `core/agents/__init__.py`:

```python
registry.register(AgentSpec(
    name="python-characterization-tester",
    role=AgentRole.EXECUTOR,
    description="Write characterization tests for uncovered source files",
    scope="file",
    produces=CharTestResult,
    consumes=CoverageResult,
    make=make_python_characterization_tester,
))

registry.register(AgentSpec(
    name="python-structural-refactorer",
    role=AgentRole.EXECUTOR,
    description="Execute scoped structural refactoring (cycles, layering, splitting, naming)",
    scope="file",
    produces=StructuralRefactorResult,
    consumes=StructuralReport,
    make=make_python_structural_refactorer,
))
```

## File Layout (new files)

```
codemonkeys/
  core/agents/
    python_characterization_tester.py   # NEW — agent factory
    python_structural_refactorer.py     # NEW — agent factory
  artifacts/schemas/
    structural.py                       # NEW — StructuralReport, FileMetrics, etc.
    coverage.py                         # NEW — CoverageResult, FileCoverage
    health.py                           # NEW — BuildCheckResult, DependencyHealthResult
    refactor.py                         # NEW — StructuralRefactorResult, CharTestResult
  workflows/phase_library/
    stabilize.py                        # NEW — build_check, dependency_health, coverage_measurement
    structural.py                       # NEW — structural_analysis, characterization_tests
    refactor.py                         # NEW — refactor_step, update_readme, final_verify
  workflows/compositions.py             # MODIFIED — add make_deep_clean_workflow()
  run_review.py                         # MODIFIED — add --deep-clean flag, _resolve_mode, _pick_workflow
```

## What This Does NOT Do

- Does not replace the existing `--repo` review workflow
- Does not auto-commit changes (user controls git)
- Does not modify code without gate approval for structural changes
- Does not touch files outside the project directory
- Does not require specific project type detection (universal import check)
