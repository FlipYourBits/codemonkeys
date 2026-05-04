---
name: python-review
description: "Full Python code review: mechanical checks (pyright, pytest, ruff, coverage, pip-audit) plus quality, security, changelog, and README review. Presents findings and fixes on approval."
allowed-tools: Bash(python -m *) Bash(git diff *) Bash(git ls-files *) Bash(git log *)
---

Read and follow `shared/engineering-mindset.md` and `shared/python-guidelines.md` before proceeding.

## Step 1 — Determine scope

If the user passed files or directories in the prompt (e.g., `/codemonkeys:python-review src/auth.py src/models.py`), use those as scope — skip the scope question.

If no files were specified, present these three options to the user:

1. **Diff** (changes vs main) — will use `git diff main...HEAD`
2. **Entire repo** — will review all Python source files
3. **Specific files** — ask which files or directories to review

Wait for the user's answer before proceeding.

## Step 2 — Ask exclusions

Present all review categories with descriptions:

| Category | Description |
|----------|-------------|
| Quality review | Naming, design, complexity, patterns |
| Security audit | Injection, auth, secrets, deserialization |
| Type checking | pyright |
| Tests & coverage | pytest with coverage |
| Lint & format check | ruff |
| Dependency audit | pip-audit |
| Changelog review | Compare CHANGELOG.md vs git history |
| README review | Compare README.md vs codebase |

Ask: "Want to skip any of these?"

Wait for the user's answer before proceeding.

## Step 3 — Read code

Based on the scope chosen in Step 1:

- **Diff**: run `git diff main...HEAD -- '*.py'` to get the diff, then read the changed files in full.
- **Repo**: run `git ls-files '*.py'` to list all tracked Python files (this automatically excludes `.venv/`, `__pycache__/`), then read the source files.
- **Specific**: read the files or directories the user specified.

Only read git-tracked files. Skip `.venv/`, `__pycache__/`, `*.pyc`, `*.egg-info/`.

## Step 4 — Run mechanical checks

Run these checks directly. For each non-excluded category:

- `python -m ruff check --output-format json <scope>` (lint)
- `python -m pyright --outputjson <scope>` (type checking)
- `python -m pytest --cov --cov-report=json --cov-report=term -x -q --tb=short --no-header` (tests & coverage)
- `python -m pip_audit --format json --strict --desc` (dependency audit)

Where `<scope>` is the files/directories from Step 1 (or `.` for full repo).

Handle missing tools gracefully — if a tool is not installed, note it and continue with the remaining categories.

## Step 5 — Apply review checklists

### Quality Review

Check these categories. Only report findings at 80%+ confidence.

#### `naming`

- Variable/function names that don't describe intent (`data`, `result`, `tmp`, `x` outside comprehensions)
- Names that describe type instead of meaning (`user_dict` -> `users_by_id`)
- Boolean variables/functions missing is_/has_/can_/should_ prefix
- Abbreviations that aren't universally understood
- Names that shadow builtins (`list`, `type`, `id`, `input`)
- Misleading names — function does X but is named Y

#### `function_design`

- Functions longer than ~40 lines — suggest extracting a helper
- Functions with more than 4 parameters — suggest a config dataclass
- Deeply nested conditionals (3+ levels) — suggest early returns
- Functions that do more than one thing — suggest splitting
- Side effects hidden in functions that look pure
- Boolean parameters that change behavior — suggest separate functions

#### `class_design`

- God classes — more than ~10 public methods or mixed responsibilities
- Classes with only `__init__` — should be a `dataclass`
- Deep inheritance hierarchies (3+ levels) — suggest composition
- Mutable class attributes shared across all instances

#### `documentation`

- Public functions/classes missing docstrings
- Docstring that doesn't match the current signature
- Docstring examples that use renamed or removed APIs
- Docstring that restates the function name without adding value

#### `error_handling`

- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging (`except SomeError: pass`)
- Try/except block that's too wide

#### `code_structure`

- Dead code — unreachable branches, unused imports/functions
- Commented-out code blocks
- Duplicated logic that has drifted between copies
- Magic numbers/strings without named constants

#### `complexity`

The bar: a junior developer should understand any piece of code within 30 seconds.

- Abstraction layers that add indirection without value
- Premature generalization — flexibility that isn't used
- Clever-over-clear patterns (metaclasses, descriptor magic where plain code works)
- Over-engineered design patterns where if/else suffices

For each complexity finding, include a simplified alternative.

#### `pythonic_patterns`

- Resources opened without context managers
- Manual loops where comprehensions would be clearer
- Plain dicts for structured data where dataclass/BaseModel fits
- `os.path` instead of `pathlib.Path`
- `.format()` or `%` instead of f-strings

#### `performance` (only flag obvious issues)

- Quadratic loops over data that could be set/dict-indexed
- String concatenation in a loop instead of `"".join()`

#### Quality exclusions — DO NOT REPORT

- Formatting/whitespace (linter owns these)
- Type errors (type checker owns these)
- Missing tests (test runner owns these)
- Security vulnerabilities (security audit owns these)
- README staleness (readme review owns these)

---

### Security Audit

Trace data flow from untrusted inputs (HTTP handlers, CLI args, env vars, queue consumers, file ingest) to sinks. Only report genuinely exploitable findings with concrete attack scenarios.

#### `injection`

- SQL via string concatenation instead of parameterized queries
- NoSQL injection — user-controlled dicts passed to find/update without sanitizing operators
- Command injection via `subprocess` with `shell=True` and user input, or `os.system()`
- LDAP injection — user input concatenated into filter strings
- Path traversal — user-controlled paths without confining to a base dir
- SSRF — outbound requests built from user input without host allowlist
- Template injection — user input rendered as a template instead of data
- Log injection — user strings logged without newline sanitization
- XXE — XML parsing without disabling external entity resolution

#### `authentication & authorization`

- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without ownership check
- JWT: `alg=none` bypass, missing expiry validation, weak signing keys
- Session fixation — session ID not regenerated after login
- CSRF — state-changing endpoints without anti-CSRF tokens
- Mass assignment — ORM objects created with unfiltered request data

#### `secrets & crypto`

- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of bcrypt/argon2)
- `random` module used for security-critical values (use `secrets`)
- TLS verification disabled (`verify=False`)
- Non-constant-time token comparison (use `hmac.compare_digest`)

#### `unsafe deserialization & code execution`

- `pickle.loads()` / `yaml.load()` on untrusted input
- `eval()` / `exec()` with user-controlled strings

#### `output & transport security`

- Jinja2 templates with `autoescape=False`
- Auth cookies without `httponly=True`, `secure=True`, `samesite`
- PII/credentials in logs or error responses

#### Security exclusions — DO NOT REPORT

- Code quality (quality review owns these)
- Dependency vulnerabilities (dep audit owns these)
- Test failures (test runner owns these)
- Denial of service

---

### Changelog Review

1. Read CHANGELOG.md and check the format and last released version.
2. Run `git log <last-release-tag-or-commit>..HEAD --oneline` to see changes since last release. If no tag exists, use `git log main..HEAD --oneline` or `git log --oneline -30` as fallback.
3. Read changed files to understand what each commit actually does — don't rely on commit messages alone.
4. Compare git history against the changelog.

keepachangelog categories: Added, Changed, Deprecated, Removed, Fixed, Security.

Finding categories:

#### `missing_entry`

A commit introduces a user-facing change with no corresponding changelog entry.

#### `stale_entry`

Changelog describes a feature that has been renamed or removed in a later commit.

#### `wrong_category`

Entry is in the wrong keepachangelog category.

#### `format_issue`

Missing or malformed version header, inconsistent date format.

Only report significant user-facing changes. Deduplicate related findings.

---

### README Review

1. Read README.md and project metadata (`pyproject.toml`, `package.json`, etc.).
2. Use `git ls-files` to discover project structure.
3. Read key source files to verify claims.
4. Cross-reference every claim: import paths, CLI commands, function names, config options, examples.

Check for missing sections: description, prerequisites, installation, quick start, usage, license, contributing.

Finding categories:

#### `stale_reference`

References a renamed or deleted function, class, module, or CLI command.

#### `broken_example`

Code example would fail if copy-pasted.

#### `missing_section`

A required section is absent or empty.

#### `inaccurate_metadata`

Package name, version, or deps don't match project metadata.

#### `incomplete_docs`

Major feature exists in code but is not documented.

#### `quality`

Contradictory info, wrong order, assumes prior knowledge without stating prerequisites.

Deduplicate — if the same rename broke 5 references, report it once.

## Step 6 — Present findings

Group findings by category. Show severity counts at the top:

> **N findings total (X high, Y medium, Z low).**

Summarize each category in 2-3 sentences, then list individual findings. Each finding must include:

- **File** and **line**
- **Severity**: HIGH / MEDIUM / LOW
- **Category**
- **Description**
- **Recommendation**

## Step 7 — Ask which to fix

Ask: "Which findings should I fix? Options: 'all', 'high only', list specific numbers, or 'none'."

Wait for the user's answer before proceeding.

## Step 8 — Apply fixes

For each approved finding:

1. Read the file and surrounding context.
2. Make the smallest correct change.
3. If coverage gaps were selected, write tests for uncovered code.

## Step 9 — Verify-fix loop

After applying fixes:

1. Run `ruff check --fix .` and `ruff format .` on changed files. If ruff is not installed, skip.
2. Run `python -m pyright .` and `python -m pytest -x -q --tb=short --no-header` to confirm fixes didn't introduce new issues.

Maximum 2 cycles. If still failing after cycle 2, **STOP** and report:

1. Which checks still fail and the specific errors
2. What was tried
3. Hypothesis for why it persists

## Step 10 — Report

Summarize:

- What was fixed
- What still fails
- What was skipped

## Rules

- Each review category stays in its lane — no overlap between quality, security, changelog, and README reviews.
- Never exceed 2 verify-fix cycles.
- Always ask before fixing — never auto-fix.
- Zero findings is a valid result.
