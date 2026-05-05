# Codemonkeys

Python code review and development toolkit powered by Claude Agent SDK. Engineering judgment, workflow, and standards encoded as agent pipelines.

## Project Structure

```
codemonkeys/
  core/
    agents/                     # Agent factories (return AgentDefinition)
    prompts/                    # Shared prompt templates (quality, security, guidelines)
    analysis.py                 # AST-based file analysis
    runner.py                   # AgentRunner with Rich live display
  artifacts/schemas/            # Pydantic schemas (findings, architecture, results)
  workflows/                    # State-machine orchestration (review, implement)
  run_review.py                 # CLI review pipeline (standalone)
  tui/                          # Textual TUI (in progress)
tests/                          # Test suite
docs/codemonkeys/
  specs/                        # Design specs
  plans/                        # Approved feature plans
.claude/
  settings.local.json           # Dev permissions
```

## How to Work Here

**Run review pipeline:**
```
uv run python -m codemonkeys.run_review --diff
uv run python -m codemonkeys.run_review --repo
uv run python -m codemonkeys.run_review --files path/a.py path/b.py
```

**Lint/format:**
```
ruff check --fix . && ruff format .
```

**Type check:**
```
pyright .
```

## Architecture Decisions

- **Workflows coordinate, agents implement.** `implement` workflow designs and gets approval; `python_implementer` agent writes code via TDD. The plan file is the contract between them.
- **Hard gates before action.** The implement workflow does not dispatch the implementer until the user explicitly approves the plan.
- **Agent-based review pipeline.** `run_review.py` dispatches per-file reviewer agents in parallel (batched up to 3 files, model-tiered: haiku for tests, sonnet for prod), then an architecture reviewer (opus). Agents return structured JSON findings via output schemas.
- **Reusable prompt templates.** `code_quality`, `security_observations`, and `python_guidelines` are shared prompts loaded into agent system prompts. When adding a new language, create new guidelines and a file-reviewer agent — the core checklists are shared.
- **Debug logging.** Every agent run writes a `.log` (raw JSONL events) and `.md` (readable system prompt + user prompt + structured output) to `.codemonkeys/logs/<timestamp>/`.

## Agents

- `python_file_reviewer` — reviews 1-3 Python files for quality/security (sonnet or haiku)
- `architecture_reviewer` — cross-file design review (opus)
- `python_code_fixer` — applies fixes from review findings (sonnet)
- `changelog_reviewer` — reviews CHANGELOG.md vs git history (haiku)
- `readme_reviewer` — verifies README.md claims (sonnet)
- `python_implementer` — TDD implementation from plan (opus)

## Detailed Docs (Read When Relevant)

- `docs/codemonkeys/specs/` — design specs
- `docs/codemonkeys/plans/` — feature plans
- `README.md` — installation, usage
