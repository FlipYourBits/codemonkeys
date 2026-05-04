# Codemonkeys

Personal development methodology plugin — engineering judgment, workflow, and standards encoded as Claude Code skills. Currently Python-focused, expanding to other ecosystems.

## Project Structure

```
.claude-plugin/
  plugin.json                 # Plugin manifest
skills/                       # Slash-command workflows (namespaced as codemonkeys:*)
  */SKILL.md
agents/                       # Subagents dispatched by skills
  *.md
docs/codemonkeys/plans/       # Approved feature plans (committed)
.claude/
  settings.local.json         # Dev permissions (not shipped)
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
- **Agent-based review pipeline.** `python-review` dispatches per-file subagents in parallel for quality and security review, plus dedicated agents for changelog and README review. The orchestrator never reads source files — it runs CLI tools, collects structured JSON findings, and presents results.
- **Reusable sub-skills.** `code-quality` and `security-observations` are language-agnostic checklists loaded by file-reviewer agents. When adding a new language, create a new guidelines skill and file-reviewer agent — the core checklists are shared.
- **No hooks.** Skills know *when* to run checks (formatting, tests, branch management) with better context than event-driven hooks. Each skill manages its own workflow.

## Skills & Agents

**User-invocable skills:**
- `python-review` — orchestrates parallel code review via agents
- `python-feature` — design-to-implementation workflow
- `project-architecture` — generates/updates architecture docs

**Dependency skills (non-invocable, loaded by agents):**
- `engineering-mindset` — core engineering principles
- `python-guidelines` — Python conventions
- `code-quality` — language-agnostic quality checklist
- `security-observations` — language-agnostic security checklist

**Agents:**
- `python-file-reviewer` — reviews one Python file (sonnet)
- `changelog-reviewer` — reviews CHANGELOG.md vs git history (haiku)
- `readme-reviewer` — verifies README.md claims (sonnet)
- `python-implementer` — TDD implementation from plan (opus)

## Detailed Docs (Read When Relevant)

- `skills/*/SKILL.md` — full skill specifications
- `agents/*.md` — agent specs
- `docs/codemonkeys/specs/` — design specs
- `README.md` — installation, usage
