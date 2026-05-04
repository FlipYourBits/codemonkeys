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
