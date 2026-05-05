# codemonkeys

Skill-driven workflows for Python development in [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Provides structured code review via parallel agents, feature implementation with TDD, and engineering standards — all as Claude Code skills.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python 3.10+

### Optional Tool Dependencies

Skills run these tools as part of their workflows. Missing tools are skipped gracefully:

| Tool | Used by | Install |
|------|---------|---------|
| ruff | codemonkeys-python-review, codemonkeys-python-feature | `pip install ruff` |
| pyright | codemonkeys-python-review | `pip install pyright` |
| pytest | codemonkeys-python-review, codemonkeys-python-feature | `pip install pytest` |
| pip-audit | codemonkeys-python-review | `pip install pip-audit` |

To install everything:

```bash
pip install ruff pyright pytest pip-audit
```

## Installation

Install as a Claude Code plugin by adding it to your project's `.claude/settings.json`:

```json
{
  "plugins": [
    "/absolute/path/to/codemonkeys"
  ]
}
```

Or install for all projects via `~/.claude/settings.json`.

Restart Claude Code (or start a new conversation) to load the plugin. Skills will be available as `/codemonkeys-python-feature`, `/codemonkeys-python-review`, etc.

## Uninstall

Remove the plugin path from your `.claude/settings.json` `plugins` array and restart Claude Code.

## Skills

### codemonkeys-python-feature

Design-to-implementation workflow for Python features. Walks you from idea to working code through a structured planning process, then dispatches the `codemonkeys-python-implementer` agent to build it with TDD.

**Example — start a new feature:**

```
/codemonkeys-python-feature add rate limiting to the API
```

**Example — resume an in-progress plan:**

```
/codemonkeys-python-feature
> Found an in-progress plan: docs/codemonkeys/plans/2026-05-01-rate-limiting.md
> Continue where we left off, or start fresh?
```

**Workflow:**

First, a **resume check** scans `docs/codemonkeys/plans/` for in-progress plans and offers to resume or start fresh. Then:

1. **Explore context** — creates a plan file in `docs/codemonkeys/plans/`, reads the codebase, and records what it learns.
2. **Clarifying questions** — asks one question at a time to understand purpose, constraints, and acceptance criteria. Each answer is saved to the plan file.
3. **Propose approaches** — presents 2-3 approaches with tradeoffs and a recommendation. User picks one.
4. **Present design** — walks through architecture, components, data flow, and error handling section by section with approval at each step.
5. **Finalize plan** — rewrites the plan into its final form. Waits for explicit user approval before proceeding.
6. **Branch check** — if on main/master, suggests a feature branch name and offers to create it.
7. **Dispatch implementer** — spawns the `codemonkeys-python-implementer` agent with only the plan file as context.
8. **Verify and format** — runs ruff and pytest after implementation. Fixes test failures (max 2 cycles).
9. **Report** — summarizes files changed, test results, and anything skipped.

The plan file survives context compaction — if Claude loses the skill context mid-workflow, re-invoking the skill picks up where it left off.

### codemonkeys-python-review

Full Python code review dispatching parallel agents for quality, security, changelog, and README review. Runs mechanical checks via CLI tools. The orchestrator never reads source files directly — agents handle that.

**Example — review changes on the current branch:**

```
/codemonkeys-python-review
> 1. Diff (changes vs main)    ← select this
```

**Example — review specific files:**

```
/codemonkeys-python-review src/auth.py src/models.py
```

**Example — skip categories you don't need:**

```
/codemonkeys-python-review
> Want to skip any of these?
> skip changelog and README
```

**Workflow:**

1. **Determine scope** — review a diff vs main, the entire repo, or specific files. Files passed in the command are used directly.
2. **Ask exclusions** — presents all review categories (file review agents, ruff, pyright, pytest, pip-audit, changelog, README) and asks if any should be skipped.
3. **Run mechanical checks** — runs ruff (lint), pyright (types), pytest (tests + coverage), and pip-audit (dependency vulnerabilities) directly. Missing tools are skipped gracefully.
4. **Dispatch review agents** — spawns a `codemonkeys-python-file-reviewer` agent per file (for code quality, security, and Python conventions), plus `codemonkeys-changelog-reviewer` and `codemonkeys-readme-reviewer` agents. All run in parallel.
5. **Collect and merge findings** — parses structured JSON from each agent, deduplicates against mechanical check results, and sorts by severity.
6. **Present findings** — groups findings by category with severity counts. Each finding includes file, line, severity, description, and recommendation.
7. **Ask which to fix** — user chooses all, high-only, specific numbers, or none.
8. **Apply fixes** — makes the smallest correct change for each approved finding.
9. **Verify-fix loop** — runs ruff, pyright, and pytest to confirm fixes didn't introduce new issues. Max 2 cycles.
10. **Report** — summarizes what was fixed, what still fails, and what was skipped.

### Dependency Skills

These skills are loaded automatically by agents and other skills. Not user-invocable.

- **codemonkeys-python-guidelines** — Python conventions: `from __future__ import annotations`, type hints on all public functions, Pydantic BaseModel for structured data, pathlib over os.path, f-strings, context managers, short single-purpose functions, no dead code.
- **codemonkeys-engineering-mindset** — Core engineering principles: understand before acting, plan first, architecture-first debugging, TDD for bug fixes, KISS, the junior dev test, no hacks, fail loudly at boundaries, test behavior not implementation, severity-based prioritization.
- **codemonkeys-code-quality** — Language-agnostic quality checklist: naming, design, complexity, structure. Loaded by file-reviewer agents.
- **codemonkeys-security-observations** — Language-agnostic security checklist: injection, auth, secrets, deserialization. Loaded by file-reviewer agents.

## Agents

### codemonkeys-python-file-reviewer

Reviews a single Python file for code quality, security, and Python conventions. Dispatched by `codemonkeys-python-review` — not invoked directly. Returns structured JSON findings covering naming, design, complexity, Python conventions (type hints, pathlib, etc.), injection, auth, secrets, and deserialization.

### codemonkeys-changelog-reviewer

Compares git history against CHANGELOG.md for accuracy. Dispatched by `codemonkeys-python-review` — not invoked directly. Returns structured JSON findings.

### codemonkeys-readme-reviewer

Verifies README.md claims against the actual codebase. Dispatched by `codemonkeys-python-review` — not invoked directly. Returns structured JSON findings.

### codemonkeys-python-implementer

Implements features, updates, and bug fixes from an approved plan file using TDD. Dispatched by `codemonkeys-python-feature` — not invoked directly.

**Method:**

1. Read the plan and identify every file that needs to change.
2. Read existing code to understand architecture and patterns.
3. Write failing tests first, then implement code to make them pass.
4. Work through remaining changes one file at a time.
5. Run ruff to format all changed files.
6. Run the test suite to verify nothing is broken.
7. Fix any test failures (max 3 cycles, then stop and report).

**Constraints:** implements exactly what the plan describes — no extras, no refactoring, no "improvements." Does not commit or push. If something is ambiguous, makes the simplest choice and notes it. If something is impossible, skips it and explains why.

## Sandbox

`sandbox.py` provides OS-level filesystem sandboxing — once activated, the process and all children can only write inside the project directory. Reads are unrestricted. The restriction is irrevocable for the lifetime of the process.

**API:**

- `restrict(project_dir)` — apply the sandbox. Safe to call multiple times (subsequent calls are no-ops).
- `is_restricted()` — check whether the sandbox is active.

**Platform backends:**

| Platform | Backend | Requirement |
|----------|---------|-------------|
| Linux | Landlock LSM | Kernel 5.13+, `pip install landlock` |
| macOS | sandbox-exec (Seatbelt) | Built-in (re-execs the process) |
| Windows | Low Integrity Token | Built-in (re-execs the process) |

On unsupported platforms, `restrict()` logs a warning and returns without applying any restriction.

Write access is always granted to `/tmp`, `/dev`, and Claude CLI state directories (`~/.claude`, `~/.local/share/claude`) in addition to the project directory.

## License

[MIT](LICENSE)
