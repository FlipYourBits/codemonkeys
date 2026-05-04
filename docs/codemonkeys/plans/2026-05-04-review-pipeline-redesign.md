---
status: approved
feature: review-pipeline-redesign
created: 2026-05-04
---

# Review Pipeline Redesign Implementation Plan

> **For agentic workers:** Implement each task sequentially. Tasks 1-2 are independent sub-skills. Tasks 3-5 are independent agents. Task 6 depends on all prior tasks. Task 7 is cleanup.

**Goal:** Decompose the monolithic python-review skill into parallel per-file subagents with a lean orchestrator that never reads source files.

**Architecture:** Sub-skills define review checklists (loaded by agents). Agents review single files/documents and return structured JSON. The orchestrator dispatches agents in parallel, runs CLI tools, merges findings, and presents results.

---

## Task 1: Create code-quality sub-skill

**Files:**
- Create: `skills/code-quality/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `skills/code-quality/SKILL.md` with the language-agnostic quality checklist extracted from the current python-review skill. This skill is non-invocable — loaded by file-reviewer agents as a dependency.

```markdown
---
name: code-quality
description: Language-agnostic code quality checklist — naming, design, complexity, structure
user-invocable: false
---

## Code Quality Review Checklist

Review the file for quality issues. Only report findings at 80%+ confidence. Return findings using the structured JSON format specified in your prompt.

### naming

- Variable/function names that don't describe intent (`data`, `result`, `tmp`, `x` outside comprehensions)
- Names that describe type instead of meaning (`user_dict` → `users_by_id`)
- Boolean variables/functions missing is_/has_/can_/should_ prefix
- Abbreviations that aren't universally understood
- Names that shadow builtins (`list`, `type`, `id`, `input`)
- Misleading names — function does X but is named Y

### function_design

- Functions longer than ~40 lines — suggest extracting a helper
- Functions with more than 4 parameters — suggest a config dataclass
- Deeply nested conditionals (3+ levels) — suggest early returns
- Functions that do more than one thing — suggest splitting
- Side effects hidden in functions that look pure
- Boolean parameters that change behavior — suggest separate functions

### class_design

- God classes — more than ~10 public methods or mixed responsibilities
- Classes with only `__init__` — should be a dataclass
- Deep inheritance hierarchies (3+ levels) — suggest composition
- Mutable class attributes shared across all instances

### documentation

- Public functions/classes missing docstrings
- Docstring that doesn't match the current signature
- Docstring examples that use renamed or removed APIs
- Docstring that restates the function name without adding value

### error_handling

- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging (`except SomeError: pass`)
- Try/except block that's too wide — wraps more code than necessary

### code_structure

- Dead code — unreachable branches, unused imports/functions
- Commented-out code blocks
- Duplicated logic that has drifted between copies
- Magic numbers/strings without named constants

### complexity

The bar: a junior developer should understand any piece of code within 30 seconds.

- Abstraction layers that add indirection without value
- Premature generalization — flexibility that isn't used
- Clever-over-clear patterns (metaclasses, descriptor magic where plain code works)
- Over-engineered design patterns where if/else suffices

For each complexity finding, include a simplified alternative in the recommendation.

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Formatting/whitespace (linter owns these)
- Type errors (type checker owns these)
- Missing tests (test runner owns these)
- Security vulnerabilities (security skill owns these)
- README/changelog staleness (their own agents own these)
```

- [ ] **Step 2: Verify skill is discoverable**

Run: `ls skills/code-quality/SKILL.md`
Expected: file exists

---

## Task 2: Create security-observations sub-skill

**Files:**
- Create: `skills/security-observations/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `skills/security-observations/SKILL.md` with the per-file security checklist extracted from the current python-review skill. Non-invocable — loaded by file-reviewer agents.

```markdown
---
name: security-observations
description: Per-file security vulnerability checklist — injection, auth, secrets, deserialization
user-invocable: false
---

## Security Review Checklist

Review the file for security vulnerabilities. Only report genuinely exploitable findings with concrete attack scenarios. Return findings using the structured JSON format specified in your prompt.

### injection

- SQL via string concatenation or f-strings instead of parameterized queries
- NoSQL injection — user-controlled dicts passed to find/update without sanitizing operators
- Command injection via `subprocess` with `shell=True` and user input, or `os.system()`
- LDAP injection — user input concatenated into filter strings
- Path traversal — user-controlled paths without confining to a base directory
- SSRF — outbound requests built from user input without host allowlist
- Template injection — user input rendered as a template instead of data
- Log injection — user strings logged without newline sanitization
- XXE — XML parsing without disabling external entity resolution

### auth

- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without ownership check
- JWT: `alg=none` bypass, missing expiry validation, weak signing keys
- Session fixation — session ID not regenerated after login
- CSRF — state-changing endpoints without anti-CSRF tokens
- Mass assignment — ORM objects created with unfiltered request data

### secrets

- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of bcrypt/argon2)
- `random` module used for security-critical values (use `secrets`)
- TLS verification disabled (`verify=False`)
- Non-constant-time token comparison (use `hmac.compare_digest`)

### deserialization

- `pickle.loads()` / `yaml.load()` on untrusted input (use `yaml.safe_load()`)
- `eval()` / `exec()` with user-controlled strings

### output_security

- Jinja2 templates with `autoescape=False`
- Auth cookies without `httponly=True`, `secure=True`, `samesite`
- PII/credentials in logs or error responses

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Code quality issues (code-quality skill owns these)
- Dependency vulnerabilities (pip-audit owns these)
- Test failures (test runner owns these)
- Denial of service (out of scope)
```

- [ ] **Step 2: Verify skill is discoverable**

Run: `ls skills/security-observations/SKILL.md`
Expected: file exists

---

## Task 3: Create python-file-reviewer agent

**Files:**
- Create: `agents/python-file-reviewer.md`

- [ ] **Step 1: Write the agent file**

Create `agents/python-file-reviewer.md`. This agent reviews a single Python file for code quality and security, returning structured JSON findings.

```markdown
---
name: python-file-reviewer
description: Reviews a single Python file for code quality and security, returns structured JSON findings
model: sonnet
tools: Read, Bash, Grep
skills:
  - code-quality
  - security-observations
  - python-guidelines
---

You review a single Python file. Read the file, apply the code-quality, security-observations, and python-guidelines checklists, then return your findings as structured JSON.

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping — just the JSON:

```json
{
  "file": "<file path as given to you>",
  "summary": "<one sentence describing what this file does>",
  "findings": [
    {
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "<quality|security>",
      "subcategory": "<specific check name>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }
  ]
}
```

## Rules

- Only report findings at 80%+ confidence
- `line` is null only when the finding is about something missing or document-wide
- `category` is either `quality` or `security`
- `subcategory` must match one of the checklist headings from your loaded skills (e.g., `naming`, `function_design`, `injection`, `secrets`)
- If the file has no issues, return an empty findings array
- Do NOT report formatting issues (linter handles those) or type errors (type checker handles those)
- Do NOT read other files — review only the file specified in your prompt
```

- [ ] **Step 2: Verify agent is discoverable**

Run: `ls agents/python-file-reviewer.md`
Expected: file exists

---

## Task 4: Create changelog-reviewer agent

**Files:**
- Create: `agents/changelog-reviewer.md`

- [ ] **Step 1: Write the agent file**

Create `agents/changelog-reviewer.md`. This agent compares git history against CHANGELOG.md and returns structured findings.

```markdown
---
name: changelog-reviewer
description: Compares git history against CHANGELOG.md, returns structured JSON findings
model: haiku
tools: Read, Bash
---

You review CHANGELOG.md for accuracy against git history.

## Method

1. Read CHANGELOG.md. Note the format and last released version.
2. Find the last release reference point:
   - Run `git tag --sort=-creatordate | head -5` to find recent tags
   - If tags exist, use the latest as the baseline: `git log <tag>..HEAD --oneline`
   - If no tags, use `git log main..HEAD --oneline` or `git log --oneline -30` as fallback
3. For each commit in the log, read the changed files to understand what it actually does — don't rely on commit messages alone.
4. Compare: are all user-facing changes reflected in the changelog?

keepachangelog categories: Added, Changed, Deprecated, Removed, Fixed, Security.

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping — just the JSON:

```json
{
  "file": "CHANGELOG.md",
  "summary": "<one sentence about changelog state>",
  "findings": [
    {
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "changelog",
      "subcategory": "<missing_entry|stale_entry|wrong_category|format_issue>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }
  ]
}
```

## Rules

- `line` is the line in CHANGELOG.md where the issue is, or null for missing entries
- Only report significant user-facing changes — internal refactors don't need changelog entries
- Deduplicate: if 5 related commits are all missing, report once with a summary
- If CHANGELOG.md doesn't exist, return a single finding: missing_entry, "No CHANGELOG.md file exists"
- If the changelog is accurate and complete, return an empty findings array
```

- [ ] **Step 2: Verify agent is discoverable**

Run: `ls agents/changelog-reviewer.md`
Expected: file exists

---

## Task 5: Create readme-reviewer agent

**Files:**
- Create: `agents/readme-reviewer.md`

- [ ] **Step 1: Write the agent file**

Create `agents/readme-reviewer.md`. This agent verifies README.md claims against the actual codebase.

```markdown
---
name: readme-reviewer
description: Verifies README.md claims against actual codebase, returns structured JSON findings
model: sonnet
tools: Read, Bash, Grep
---

You review README.md for accuracy by verifying its claims against the actual codebase.

## Method

1. Read README.md and project metadata (`pyproject.toml`, `setup.cfg`, `package.json`, etc.).
2. For every concrete claim in the README:
   - Import paths: grep to verify they exist
   - CLI commands: grep for argument parser or command registration
   - Function/class names: grep to verify they exist and have the described signature
   - Config options: grep to verify they're used
   - Code examples: verify imports and function calls would work
3. Check for required sections: description, prerequisites, installation, quick start, usage, license.
4. Check for undocumented major features (public modules/commands not mentioned in README).

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping — just the JSON:

```json
{
  "file": "README.md",
  "summary": "<one sentence about README state>",
  "findings": [
    {
      "line": <int or null>,
      "severity": "<HIGH|MEDIUM|LOW>",
      "category": "readme",
      "subcategory": "<stale_reference|broken_example|missing_section|inaccurate_metadata|incomplete_docs|quality>",
      "description": "<what's wrong>",
      "recommendation": "<how to fix it>"
    }
  ]
}
```

## Subcategories

- **stale_reference** — references a renamed or deleted function, class, module, or CLI command
- **broken_example** — code example would fail if copy-pasted
- **missing_section** — a required section (description, prerequisites, install, usage, license) is absent
- **inaccurate_metadata** — package name, version, or deps don't match project metadata
- **incomplete_docs** — major feature exists in code but is not documented in README
- **quality** — contradictory info, wrong order, assumes prior knowledge without stating prerequisites

## Rules

- `line` is the line in README.md where the bad claim is, or null for missing sections
- Deduplicate — if the same rename broke 5 references, report it once
- If README.md doesn't exist, return a single finding: missing_section, "No README.md file exists"
- If the README is accurate and complete, return an empty findings array
```

- [ ] **Step 2: Verify agent is discoverable**

Run: `ls agents/readme-reviewer.md`
Expected: file exists

---

## Task 6: Rewrite python-review orchestrator skill

**Files:**
- Modify: `skills/python-review/SKILL.md` (full rewrite)

- [ ] **Step 1: Rewrite the skill file**

Replace the entire contents of `skills/python-review/SKILL.md` with the new orchestrator that dispatches agents instead of reading files itself.

```markdown
---
name: python-review
description: "Full Python code review — dispatches parallel agents for quality, security, changelog, and README. Runs mechanical checks via CLI tools. Never reads source files directly."
skills:
  - engineering-mindset
---

## Step 1 — Determine scope

If the user passed files or directories in the prompt (e.g., `/python-review src/auth.py src/models.py`), use those as scope — skip the scope question.

If no files were specified, present these options:

1. **Diff** (changes vs main) — `git diff main...HEAD --name-only -- '*.py'`
2. **Entire repo** — `git ls-files '*.py'`
3. **Specific files** — ask which files or directories

Wait for the user's answer before proceeding.

## Step 2 — Ask exclusions

Present all review categories:

| Category | Agent/Tool |
|----------|-----------|
| Code quality + Security | python-file-reviewer agents |
| Lint & format | ruff (CLI) |
| Type checking | pyright (CLI) |
| Tests & coverage | pytest (CLI) |
| Dependency audit | pip-audit (CLI) |
| Changelog review | changelog-reviewer agent |
| README review | readme-reviewer agent |

Ask: "Want to skip any of these?"

Wait for the user's answer before proceeding.

## Step 3 — Run mechanical checks

Run non-excluded CLI tools directly (no agents needed):

- `python -m ruff check --output-format json <scope>`
- `python -m pyright --outputjson <scope>`
- `python -m pytest --cov --cov-report=json --cov-report=term -x -q --tb=short --no-header`
- `python -m pip_audit --format json --strict --desc`

Where `<scope>` is the files/directories from Step 1 (or `.` for full repo).

Handle missing tools gracefully — if a tool is not installed, note it and skip. Convert JSON output to the standard findings format:

```json
{"line": <int>, "severity": "<HIGH|MEDIUM|LOW>", "category": "<lint|type|test|dependency>", "subcategory": "<tool-specific>", "description": "...", "recommendation": "..."}
```

## Step 4 — Dispatch all review agents in parallel

For each Python file in scope, dispatch a `python-file-reviewer` agent:

```
Prompt: "Review: <file_path>"
```

If changelog review not excluded, dispatch a `changelog-reviewer` agent:

```
Prompt: "Review the changelog for accuracy against git history."
```

If README review not excluded, dispatch a `readme-reviewer` agent:

```
Prompt: "Review README.md for accuracy against the codebase."
```

All agents run simultaneously. Wait for all to complete.

## Step 5 — Collect and merge findings

- Parse JSON output from each agent
- Concatenate all findings arrays
- Add mechanical check findings from Step 3
- Deduplicate: if ruff and file-reviewer both flag the same file+line, keep the richer finding (the one with a recommendation)
- Sort by severity (HIGH first), then by file path

## Step 6 — Present findings

Show severity counts at the top:

> **N findings total (X high, Y medium, Z low).**

Group findings by category. For each finding show:
- **File:line** (or just File if line is null)
- **Severity**
- **Category > Subcategory**
- **Description**
- **Recommendation**

## Step 7 — Ask which to fix

Ask: "Which findings should I fix? Options: 'all', 'high only', list specific numbers, or 'none'."

Wait for the user's answer before proceeding.

## Step 8 — Apply fixes

For each file that has approved findings:
1. Read the file
2. Apply the smallest correct change for each finding
3. If multiple findings in the same file, fix them all in one pass

## Step 9 — Verify-fix loop

After applying fixes:

1. Run `ruff check --fix . && ruff format .` on changed files (skip if ruff not installed)
2. Run `python -m pyright <changed_files>` and `python -m pytest -x -q --tb=short --no-header`

Maximum 2 cycles. If still failing after cycle 2, STOP and report:
- Which checks still fail and the specific errors
- What was tried
- Hypothesis for why it persists

## Step 10 — Report

Summarize:
- What was fixed
- What still fails (if anything)
- What was skipped and why

## Rules

- Never read source files for review purposes — agents do that
- Each review category stays in its lane — no overlap between agents
- Never exceed 2 verify-fix cycles
- Always ask before fixing — never auto-fix
- Zero findings is a valid result
- Handle agent failures gracefully — if an agent returns invalid JSON, note it and continue with other results
```

- [ ] **Step 2: Verify skill frontmatter references are valid**

Run: `ls skills/engineering-mindset/SKILL.md`
Expected: file exists (skill dependency is valid)

---

## Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update project structure section**

Update the CLAUDE.md to reflect the new file layout including new skills and agents.

- [ ] **Step 2: Update architecture decisions**

Add a note about the agent-based review pipeline architecture.

---

## Acceptance Criteria

- [ ] `skills/code-quality/SKILL.md` exists with non-invocable quality checklist
- [ ] `skills/security-observations/SKILL.md` exists with non-invocable security checklist
- [ ] `agents/python-file-reviewer.md` exists, references code-quality + security-observations + python-guidelines
- [ ] `agents/changelog-reviewer.md` exists, self-contained
- [ ] `agents/readme-reviewer.md` exists, self-contained
- [ ] `skills/python-review/SKILL.md` rewritten as orchestrator that dispatches agents
- [ ] No skill references non-existent dependencies
- [ ] CLAUDE.md reflects new structure
