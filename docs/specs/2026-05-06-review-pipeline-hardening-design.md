# Review Pipeline Hardening Design Spec

Five new capabilities that close the remaining gaps in the review pipeline for production-readiness assessment. Two are prompt templates injected into the existing file reviewer agent, two are mechanical tools requiring zero LLM tokens, and one is a prompt template for test files.

## Capabilities

| Capability | Type | Token Cost | Injection |
|-----------|------|-----------|-----------|
| Resilience Review | Prompt template | LLM (conditional) | `full_repo` + `post_feature` modes, prod files only |
| Test Quality | Prompt template | LLM (Haiku) | Always-on, test files only |
| License Compliance | Mechanical tool | Zero | All modes |
| Release Hygiene | Mechanical tool | Zero | All modes |

## 1. `RESILIENCE_REVIEW` Prompt Template

A single prompt template bundling concurrency/async correctness, error recovery, and log hygiene. Injected into the file reviewer for prod files in thorough modes only (`full_repo`, `post_feature`). Skipped in `diff` and `files` modes to keep quick reviews fast.

**File:** `codemonkeys/core/prompts/resilience_review.py`
**Constant:** `RESILIENCE_REVIEW`

### Categories

#### `concurrency`

What to flag:
- Missing `await` on coroutine calls
- Shared mutable state across async tasks (module-level dicts/lists mutated in coroutines)
- `asyncio.gather` without `return_exceptions=True` where one failure should not kill siblings
- Synchronous blocking calls inside async functions (`time.sleep`, blocking I/O, `subprocess.run` without executor)
- Missing cancellation handling (`asyncio.CancelledError` swallowed or not propagated)
- Thread-unsafe operations without locks (shared state mutated from multiple threads)
- Race conditions in check-then-act patterns (TOCTOU)

#### `error_recovery`

What to flag:
- I/O operations (HTTP, file, DB) without timeout configuration
- Missing retry logic on transient failures (network calls, rate limits)
- No circuit-breaker or backoff on repeated failures to the same service
- Resource leaks on error paths (connections/handles not closed in `finally` or context manager)
- Cascading failure risk (one service down takes out the whole request)

What to skip (covered by `CODE_QUALITY`):
- Broad exception catching
- Missing exception handling
- General try/except patterns

#### `log_hygiene`

What to flag:
- Error/exception paths that don't log (silent failures)
- Log messages missing context (no relevant IDs, operation name, or input state)
- Sensitive data logged (passwords, tokens, PII in log output)
- Wrong log level (errors logged as `info`, debug noise at `warning`)
- Bare `logger.exception()` without a message describing what failed

What to skip (covered by `SECURITY_OBSERVATIONS`):
- PII exposure as a security vulnerability (flagged here as operational concern — different audience, same file, no double-counting)

### Integration

`make_python_file_reviewer` gains a `resilience: bool = False` parameter. When `True`, `RESILIENCE_REVIEW` is appended to the system prompt after the existing checklists.

The `file_review` phase function sets `resilience=True` when `ctx.config.mode in ("full_repo", "post_feature")`.

Findings use the existing `Finding` schema with `category="quality"` and subcategories matching the section names above (`concurrency`, `error_recovery`, `log_hygiene`).

## 2. `TEST_QUALITY` Prompt Template

A prompt template injected into the file reviewer when reviewing test files. Always-on regardless of review mode. Test files already route to Haiku, so this adds checklist weight to the cheaper model tier.

**File:** `codemonkeys/core/prompts/test_quality.py`
**Constant:** `TEST_QUALITY`

### Categories

#### `assertion_quality`

What to flag:
- Assert-free tests (test runs code but never asserts on the result)
- Tautological assertions (`assert True`, `assert x == x`, `assert isinstance(obj, object)`)
- Assertions only on type, never on value (`assert isinstance(result, dict)` but never checks content)
- Over-reliance on `mock.assert_called_once()` without verifying what was passed or returned
- Asserting on string representations instead of structured data

#### `test_design`

What to flag:
- Test name doesn't match what's actually being tested
- Single test covering multiple unrelated behaviors (should be split)
- Test duplicates implementation logic (reconstructs expected value using the same algorithm)
- Fixtures or setup that does real work the test should be verifying
- Tests that only exercise the happy path — no edge cases, no error inputs

#### `isolation`

What to flag:
- Tests that depend on execution order (shared mutable state between tests)
- Tests that hit the network, filesystem, or external services without mocking (unintentional integration tests)
- Tests that modify module-level or class-level state without cleanup

What to skip:
- Test coverage gaps (handled by mechanical coverage tool)
- Test framework conventions and naming style
- Missing tests for specific functions (that's coverage, not quality)

### Integration

`make_python_file_reviewer` gains a `test_quality: bool = False` parameter. When `True`, `TEST_QUALITY` is appended to the system prompt.

The `file_review` phase function sets `test_quality=True` for the test-file batch (which already selects Haiku as the model). This is unconditional — applies in all review modes.

Findings use the existing `Finding` schema with `category="quality"` and subcategories matching the section names above (`assertion_quality`, `test_design`, `isolation`).

## 3. `license_compliance` Mechanical Tool

A subprocess-based tool in the mechanical audit phase. Runs `pip-licenses` to inventory all installed package licenses and flags anything non-permissive.

**Schema addition to `mechanical.py`:**

```python
class LicenseFinding(BaseModel):
    package: str = Field(description="Package name")
    version: str = Field(description="Installed version")
    license: str = Field(description="License string from metadata")
    category: Literal[
        "copyleft_risk",
        "unknown_license",
        "restrictive_license",
        "non_standard_license",
    ] = Field(description="Risk category")
    severity: Literal["high", "medium", "low"] = Field(description="Risk level")
```

### Categories

| Category | Matches | Severity |
|----------|---------|----------|
| `copyleft_risk` | GPL, AGPL, LGPL | high |
| `unknown_license` | Empty, "UNKNOWN", missing metadata | medium |
| `restrictive_license` | Known non-permissive (MPL, CC-NC, etc.) | low |
| `non_standard_license` | Unrecognized license string, not a known SPDX identifier | low |

Permissive licenses that pass silently: MIT, BSD (all variants), ISC, Apache-2.0, Unlicense, PSF, Python-2.0, 0BSD.

### Implementation

**Runner function:** `_run_license_compliance()` in `mechanical.py`
1. Run `pip-licenses --format=json --with-urls --with-system`
2. Parse JSON output
3. Classify each package's license against known-permissive set
4. Return `list[LicenseFinding]` (empty if all permissive)

**Registration:**
- Added as `license_compliance: list[LicenseFinding] | None` on `MechanicalAuditResult`
- Tool name `license_compliance` added to `ALL_TOOLS` in `compositions.py`
- Enabled in all modes (fast, file-independent)

**Dependency:** `pip-licenses` added to dev dependencies in `pyproject.toml`.

## 4. `release_hygiene` Mechanical Tool

A pattern-matching tool in the mechanical audit phase. Detects development artifacts, debug code, and configuration issues that should be cleaned up before production release. Zero LLM tokens — pure regex and AST matching.

**Schema addition to `mechanical.py`:**

```python
class HygieneFinding(BaseModel):
    file: str = Field(description="File path")
    line: int | None = Field(description="Line number, if applicable")
    category: Literal[
        "debug_artifact",
        "unresolved_marker",
        "hardcoded_dev_value",
        "dependency_pinning",
    ] = Field(description="Issue category")
    detail: str = Field(description="What was found")
    severity: Literal["high", "medium", "low"] = Field(description="Risk level")
```

### Categories

#### `debug_artifact` (severity: medium)

Patterns detected:
- `import pdb` / `import ipdb` / `import pudb`
- `breakpoint()` calls
- `print()` calls in non-CLI, non-test files (heuristic: skip files in `cli/` dirs and `test_*` files)
- `import debugpy` / `debugpy.listen`

Note: `ruff` can catch `print()` (T201) and `breakpoint()` (T100) if those rules are enabled. This tool catches them regardless of ruff configuration and adds context about why they matter (release hygiene vs style).

#### `unresolved_marker` (severity: low)

Patterns detected:
- `TODO` / `FIXME` / `HACK` / `XXX` comments without an issue tracker reference (e.g., `TODO(#123)` is fine, bare `TODO` is flagged)
- `@pytest.mark.skip` without a reason string

#### `hardcoded_dev_value` (severity: high)

Patterns detected:
- `localhost` / `127.0.0.1` / `0.0.0.0` in string literals (skip test files and files matching `*config*`, `*settings*`, `*.env*`, `*example*`)
- `debug=True` / `DEBUG = True` in non-test, non-settings files
- Common dev ports in URLs (`8080`, `3000`, `5432` in string literals outside config/test)

#### `dependency_pinning` (severity: medium)

Checks:
- `pyproject.toml` dependencies without version pins (bare package names)
- Presence of a lockfile (`uv.lock`, `requirements.lock`, `poetry.lock`)

### Implementation

**Runner function:** `_run_release_hygiene(files: list[str], cwd: Path)` in `mechanical.py`
1. Scan each file with regex patterns for debug artifacts, markers, and hardcoded values
2. Skip test files and CLI files where `print()` is expected
3. Check `pyproject.toml` for unpinned deps
4. Check for lockfile existence
5. Return `list[HygieneFinding]`

**Registration:**
- Added as `release_hygiene: list[HygieneFinding] | None` on `MechanicalAuditResult`
- Tool name `release_hygiene` added to `ALL_TOOLS` in `compositions.py`
- Enabled in all modes

**No external dependencies required.**

## Changes to Existing Files

### `codemonkeys/core/prompts/__init__.py`
- Import and export `RESILIENCE_REVIEW` and `TEST_QUALITY`

### `codemonkeys/core/agents/python_file_reviewer.py`
- `make_python_file_reviewer` gains `resilience: bool = False` and `test_quality: bool = False` parameters
- When `resilience=True`, appends `RESILIENCE_REVIEW` to system prompt
- When `test_quality=True`, appends `TEST_QUALITY` to system prompt
- These are mutually exclusive in practice (resilience for prod files, test_quality for test files) but not enforced — the caller decides

### `codemonkeys/workflows/phase_library/review.py`
- `file_review` phase sets `resilience=True` when `ctx.config.mode in ("full_repo", "post_feature")`
- `file_review` phase sets `test_quality=True` for the test-file batch (unconditional)

### `codemonkeys/workflows/phase_library/mechanical.py`
- New `_run_license_compliance()` function
- New `_run_release_hygiene()` function
- Both registered in `mechanical_audit()` dispatch

### `codemonkeys/artifacts/schemas/mechanical.py`
- New `LicenseFinding` model
- New `HygieneFinding` model
- Both added as optional fields on `MechanicalAuditResult`

### `codemonkeys/workflows/compositions.py`
- `license_compliance` and `release_hygiene` added to `ALL_TOOLS`
- Both enabled in all mode tool sets

### `pyproject.toml`
- `pip-licenses` added to dev dependencies

## Token Impact

| Mode | Before | After | Delta |
|------|--------|-------|-------|
| `--diff` | baseline | +0 LLM tokens | Mechanical tools only (zero token cost) |
| `--files` | baseline | +0 LLM tokens | Mechanical tools only |
| `--repo` | baseline | +RESILIENCE_REVIEW on prod files, +TEST_QUALITY on test files | Moderate increase on thorough reviews |
| `--post-feature` | baseline | +RESILIENCE_REVIEW on prod files, +TEST_QUALITY on test files | Moderate increase on thorough reviews |

Quick review modes (`diff`, `files`) pay zero additional LLM token cost. Thorough modes get the full checklists where the added scrutiny is warranted.
