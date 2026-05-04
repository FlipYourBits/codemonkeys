# Codemonkeys

Claude Code plugin providing skill-driven workflows for Python development. Skills handle judgment work (review, design, architecture) with hard approval gates and TDD enforcement.

## Project Structure

```
.claude/
  codemonkeys/                # The Claude Code plugin
    skills/                   # Slash-command workflows (/codemonkeys:*)
    agents/                   # Subagents dispatched by skills
docs/codemonkeys/plans/                   # Approved feature plans (committed)
```

## How to Work Here

**Lint/format:**
```
ruff check --fix . && ruff format .
```

**Type check:**
```
pyright .
```

## Architecture Decisions

- **Skills coordinate, agents implement.** `python-feature` designs and gets approval; `python-implementer` writes code via TDD. The plan file is the contract between them.
- **Hard gates before action.** `python-feature` does not dispatch the implementer until the user explicitly approves the plan.
- **No hooks.** Skills know *when* to run checks (formatting, tests, branch management) with better context than event-driven hooks. Each skill manages its own workflow.

## Detailed Docs (Read When Relevant)

- `.claude/codemonkeys/skills/*/SKILL.md` — full skill specifications (includes `engineering-mindset` and `python-guidelines` as non-invocable dependency skills)
- `.claude/codemonkeys/agents/python-implementer.md` — TDD agent spec
- `README.md` — installation, usage
