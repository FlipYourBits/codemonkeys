# Review Pipeline Redesign

## Problem

The current `python-review` skill is monolithic — the orchestrator reads all files into its own context, applies all checklists, and runs all checks. This doesn't scale. At 100+ files the context window fills with raw source code before any review happens.

## Design

Decompose review into parallel per-file subagents that return structured findings. The orchestrator never reads source files — it dispatches agents, runs CLI tools, merges structured data, and presents results.

## Structured Output Format

Every review agent returns the same findings shape so the orchestrator can merge results uniformly.

### File reviewer output

```json
{
  "file": "src/api/auth.py",
  "summary": "Handles user login and JWT token issuance",
  "findings": [
    {
      "line": 42,
      "severity": "HIGH",
      "category": "security",
      "subcategory": "secrets",
      "description": "Password compared with == instead of hmac.compare_digest",
      "recommendation": "Use hmac.compare_digest() for constant-time comparison"
    }
  ]
}
```

### Changelog reviewer output

```json
{
  "file": "CHANGELOG.md",
  "summary": "Changelog review against git history",
  "findings": [
    {
      "line": null,
      "severity": "MEDIUM",
      "category": "changelog",
      "subcategory": "missing_entry",
      "description": "Commit abc123 adds JWT refresh endpoint — no changelog entry",
      "recommendation": "Add entry under 'Added' in next unreleased version"
    }
  ]
}
```

### README reviewer output

```json
{
  "file": "README.md",
  "summary": "README accuracy review against codebase",
  "findings": [
    {
      "line": 24,
      "severity": "HIGH",
      "category": "readme",
      "subcategory": "broken_example",
      "description": "Quick start uses `from myapp import create_app` but module was renamed to `myapp.factory`",
      "recommendation": "Update import to `from myapp.factory import create_app`"
    }
  ]
}
```

### Finding schema

All findings share this structure:

| Field | Type | Description |
|-------|------|-------------|
| line | int or null | Line number in the file, null when finding is missing/document-wide |
| severity | HIGH / MEDIUM / LOW | Impact level |
| category | string | quality, security, changelog, readme |
| subcategory | string | Specific check that triggered the finding |
| description | string | What's wrong |
| recommendation | string | How to fix it |

## Skills (non-invocable dependencies)

### code-quality

Language-agnostic quality checklist loaded by file-reviewer agents.

Subcategories:
- **naming** — intent over type, boolean prefixes, no shadowing builtins, no misleading names
- **function_design** — <40 lines, ≤4 params, ≤2 nesting levels, single purpose, no hidden side effects
- **class_design** — no god classes (>10 public methods), dataclass when only `__init__`, prefer composition over deep inheritance
- **documentation** — public APIs have docstrings, examples match current code
- **error_handling** — no broad `except Exception`, no swallowed errors, appropriate try/except scope
- **code_structure** — no dead code, no commented-out blocks, no magic numbers
- **complexity** — junior dev test (30 seconds to understand), no premature abstraction

Exclusions (stay in their lane): formatting (linter), types (type checker), tests (test runner), security (security skill), README/changelog (their own agents).

### security-observations

Language-agnostic per-file security checklist loaded by file-reviewer agents.

Subcategories:
- **injection** — SQL concat, command injection (shell=True), path traversal, SSRF, template injection, log injection, XXE, NoSQL operators, LDAP injection
- **auth** — bypass paths, wrong-layer authorization, IDOR, JWT issues (alg=none, missing expiry, weak keys), session fixation, CSRF, mass assignment
- **secrets** — hardcoded keys/tokens, weak hashing, insecure random, TLS verify disabled, non-constant-time comparison
- **deserialization** — pickle.loads(), yaml.load(), eval()/exec() on untrusted input
- **output_security** — autoescape disabled, cookies without httponly/secure/samesite, PII in logs/errors

### python-guidelines (existing)

Python-specific conventions loaded by file-reviewer and implementer agents. Adds:
- **pythonic_patterns** — context managers, comprehensions, pathlib, f-strings, dataclass/BaseModel
- **performance** — quadratic loops, string concat in loops (only obvious issues)
- Python conventions: `from __future__ import annotations`, type hints, Literal types, narrow exceptions

### engineering-mindset (existing)

Core engineering principles loaded by orchestrators. Unchanged.

## Agents

### python-file-reviewer

- **Model:** sonnet (per-file pattern matching, doesn't need deep reasoning)
- **Tools:** Read, Bash, Grep
- **Loaded skills:** code-quality, security-observations, python-guidelines
- **Input:** file path from orchestrator
- **Output:** structured JSON (file reviewer format above)
- **Constraint:** only report findings at 80%+ confidence

### changelog-reviewer

- **Model:** haiku (comparing two text documents)
- **Tools:** Read, Bash
- **Loaded skills:** none (self-contained)
- **Input:** prompt with instructions to compare git log against CHANGELOG.md
- **Output:** structured JSON (changelog format above)
- **Subcategories:** missing_entry, stale_entry, wrong_category, format_issue

### readme-reviewer

- **Model:** sonnet (needs to verify code claims via grep)
- **Tools:** Read, Bash, Grep
- **Loaded skills:** none (self-contained)
- **Input:** prompt with instructions to verify README claims
- **Output:** structured JSON (readme format above)
- **Subcategories:** stale_reference, broken_example, missing_section, inaccurate_metadata, incomplete_docs, quality

### python-implementer (existing)

Unchanged. Loaded skills: engineering-mindset, python-guidelines.

## Orchestrator: python-review

User-invocable skill that coordinates the entire review pipeline. Never reads source files for review purposes.

### Step 1 — Determine scope

- If args provided with the command, use those files as scope.
- Otherwise present options: Diff (vs main), Entire repo, Specific files.
- For diff: `git diff main...HEAD --name-only -- '*.py'` → file list.
- For repo: `git ls-files '*.py'` → file list.
- For specific: user's files.

### Step 2 — Ask exclusions

Present all review categories. User can skip any:

| Category | Agent/Tool |
|----------|-----------|
| Code quality + Security | python-file-reviewer agents |
| Lint & format | ruff (CLI) |
| Type checking | pyright (CLI) |
| Tests & coverage | pytest (CLI) |
| Dependency audit | pip-audit (CLI) |
| Changelog review | changelog-reviewer agent |
| README review | readme-reviewer agent |

### Step 3 — Run mechanical checks (Bash, no agents)

Run non-excluded CLI tools and parse JSON output:
- `python -m ruff check --output-format json <scope>`
- `python -m pyright --outputjson <scope>`
- `python -m pytest --cov --cov-report=json --cov-report=term -x -q --tb=short --no-header`
- `python -m pip_audit --format json --strict --desc`

Missing tools skipped gracefully. Convert output to findings format.

### Step 4 — Dispatch all review agents in parallel

```
For each file in scope:
  dispatch python-file-reviewer with: "Review: {file_path}"

If changelog not excluded:
  dispatch changelog-reviewer

If readme not excluded:
  dispatch readme-reviewer
```

All agents run simultaneously. Orchestrator waits for all to complete.

### Step 5 — Collect and merge findings

- Concatenate findings arrays from all agents
- Merge mechanical check results (ruff/pyright issues converted to findings format)
- Deduplicate: if ruff and file-reviewer both flag the same line, keep the richer finding

### Step 6 — Present findings

- Severity counts at top: **N findings total (X high, Y medium, Z low)**
- Group by category
- Each finding: file, line, severity, category, description, recommendation

### Step 7 — Ask which to fix

Options: 'all', 'high only', specific numbers, or 'none'.

### Step 8 — Apply fixes

For each file needing fixes, dispatch a fix agent with the file path + its findings list. Or handle inline if fixes are few and simple.

### Step 9 — Verify-fix loop

Run ruff + pyright + pytest. Max 2 cycles. If still failing after 2 attempts, stop and report what failed and why.

### Step 10 — Report

- What was fixed
- What still fails
- What was skipped

## Token Budget

| Agent | Context size | Model | Relative cost |
|-------|-------------|-------|---------------|
| python-file-reviewer | ~500-800 lines (1 file + checklists) | sonnet | low |
| changelog-reviewer | ~200 lines (git log + changelog) | haiku | very low |
| readme-reviewer | ~300 lines (README + grep results) | sonnet | low |
| orchestrator | ~200 lines (findings JSON + instructions, no source) | opus | moderate but lean |

For a 50-file review: 50 sonnet agents + 1 haiku + 1 sonnet + 1 opus orchestrator. The orchestrator's context stays small regardless of file count — it only holds structured JSON findings.

## File Layout After Implementation

```
skills/
  engineering-mindset/SKILL.md        (existing, non-invocable)
  code-quality/SKILL.md               (NEW, non-invocable)
  security-observations/SKILL.md      (NEW, non-invocable)
  python-guidelines/SKILL.md          (existing, non-invocable)
  python-review/SKILL.md              (REWRITE as orchestrator)
  python-feature/SKILL.md             (existing, unchanged)
  project-architecture/SKILL.md       (existing, unchanged)

agents/
  python-file-reviewer.md             (NEW)
  changelog-reviewer.md               (NEW)
  readme-reviewer.md                  (NEW)
  python-implementer.md               (existing, unchanged)
```
