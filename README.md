# codemonkeys

Skill-driven workflows for Python development in [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Provides structured code review, feature implementation with TDD, and architecture documentation — all as Claude Code skills.

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

Copy the skills and agents into your project's `.claude/` directory:

```bash
cp -r path/to/codemonkeys/.claude/skills/codemonkeys-* your-project/.claude/skills/
cp -r path/to/codemonkeys/.claude/agents/codemonkeys-* your-project/.claude/agents/
```

Create the directories first if they don't exist:

```bash
mkdir -p your-project/.claude/skills your-project/.claude/agents
```

Start Claude Code and run `/codemonkeys-python-feature` to get started.

## Uninstall

```bash
rm -rf .claude/skills/codemonkeys-* .claude/agents/codemonkeys-*
```

## Skills

### codemonkeys-python-feature

Design-to-implementation workflow for Python features. Walks you from idea to working code through a structured planning process, then dispatches the `codemonkeys-python-implementer` agent to build it with TDD.

```
/codemonkeys-python-feature
/codemonkeys-python-feature add JWT authentication to the API
```

**Workflow:**

1. **Resume check** — scans `docs/codemonkeys/plans/` for in-progress plans. If one exists, offers to resume or start fresh.
2. **Architecture check** — verifies `docs/codemonkeys/architecture.md` is current. Offers to update it first for better codebase context.
3. **Explore context** — creates a plan file in `docs/codemonkeys/plans/`, reads the codebase, and records what it learns.
4. **Clarifying questions** — asks one question at a time to understand purpose, constraints, and acceptance criteria. Each answer is saved to the plan file.
5. **Propose approaches** — presents 2-3 approaches with tradeoffs and a recommendation. User picks one.
6. **Present design** — walks through architecture, components, data flow, and error handling section by section with approval at each step.
7. **Finalize plan** — rewrites the plan into its final form. Waits for explicit user approval before proceeding.
8. **Branch check** — if on main/master, suggests a feature branch name and offers to create it.
9. **Dispatch implementer** — spawns the `codemonkeys-python-implementer` agent with only the plan file as context.
10. **Verify and format** — runs ruff and pytest after implementation. Fixes test failures (max 2 cycles).
11. **Report** — summarizes files changed, test results, and anything skipped.

The plan file survives context compaction — if Claude loses the skill context mid-workflow, re-invoking the skill picks up where it left off.

### codemonkeys-python-review

Full Python code review combining automated mechanical checks with manual review checklists. Does not spawn any agents.

```
/codemonkeys-python-review
/codemonkeys-python-review src/auth.py src/models.py
```

**Workflow:**

1. **Determine scope** — review a diff vs main, the entire repo, or specific files. Files passed in the command are used directly.
2. **Ask exclusions** — presents all 8 review categories and asks if any should be skipped.
3. **Read code** — reads the in-scope files based on the chosen scope.
4. **Run mechanical checks** — runs ruff (lint), pyright (types), pytest (tests + coverage), and pip-audit (dependency vulnerabilities) directly. Missing tools are skipped gracefully.
5. **Apply review checklists** — manual review for quality (naming, design, complexity, patterns), security (injection, auth, secrets, deserialization), changelog accuracy, and README freshness.
6. **Present findings** — groups findings by category with severity counts. Each finding includes file, line, severity, description, and recommendation.
7. **Ask which to fix** — user chooses all, high-only, specific numbers, or none.
8. **Apply fixes** — makes the smallest correct change for each approved finding.
9. **Verify-fix loop** — runs ruff and pytest to confirm fixes didn't introduce new issues. Max 2 cycles.
10. **Report** — summarizes what was fixed, what still fails, and what was skipped.

### codemonkeys-project-architecture

Builds and maintains `docs/codemonkeys/architecture.md` — a comprehensive snapshot of the project. Does not spawn any agents.

```
/codemonkeys-project-architecture
```

**Workflow:**

1. **Check freshness** — compares current HEAD commit against `.architecture-hash`. If they match, the docs are up to date and the skill stops.
2. **Incremental update** (if hash differs) — reads the git diff since the last update, reads changed files in context, and rewrites `docs/codemonkeys/architecture.md` in full.
3. **First run** (if no hash exists) — discovers all tracked files via `git ls-files`, reads source files, and writes `docs/codemonkeys/architecture.md` from scratch.
4. **Write hash** — saves the current HEAD SHA to `.architecture-hash`.

The generated document always contains: Project Overview, Architecture, File Index, Key Abstractions, and Conventions. It describes what IS, not what should be.

### codemonkeys-python-guidelines

Python code conventions loaded automatically by other skills. Not user-invocable.

Covers: `from __future__ import annotations`, type hints on all public functions, Pydantic BaseModel for structured data, pathlib over os.path, f-strings, context managers, short single-purpose functions, no dead code.

### codemonkeys-engineering-mindset

Core engineering principles loaded automatically by other skills. Not user-invocable.

Covers: understand before acting, plan first, architecture-first debugging, TDD for bug fixes, KISS, the junior dev test, no hacks, fail loudly at boundaries, test behavior not implementation, severity-based prioritization.

## Agent

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

## License

[MIT](LICENSE)
