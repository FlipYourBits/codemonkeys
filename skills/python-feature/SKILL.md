---
name: python-feature
description: "Design-to-implementation workflow for Python features. Architecture check, incremental planning with compaction resilience, branch management, then TDD implementation via python-implementer agent."
skills:
  - engineering-mindset
  - python-guidelines
---

## Hard gate

Do NOT write any code or dispatch any agent until the user has approved the plan document. This applies to every feature regardless of perceived simplicity. No exceptions.

## Step 0 — Resume check

Before starting anything, scan for in-progress plans in `docs/codemonkeys/plans/`.

### Scan for active plans

- List all `.md` files in `docs/codemonkeys/plans/`.
- For each file, read the frontmatter `status` field.
- Collect any plans where status is not `complete`, `cancelled`, `abandoned`, or absent.

### Present options

- **No active plans**: proceed to Step 1.
- **One active plan**: tell the user: "Found an in-progress plan: `<plan-path>` (status: `<status>`). Continue where we left off, or start fresh?" If starting fresh, set the plan's status to `abandoned` and proceed to Step 1.
- **Multiple active plans**: list them all with their plan paths and statuses. Ask the user which to continue, or start fresh. Set status to `abandoned` for any plan the user abandons.
- **If continuing**: read the plan file and resume from the step matching the current status (see mapping below).

### Status-to-step mapping

| Plan status | Resume from |
|-------------|-------------|
| `exploring` | Step 2 — re-read context, then continue to questions |
| `questions` | Step 3 — find unanswered questions (marked `*pending*`), continue asking |
| `approaches` | Step 4 — check if an approach was selected, present options if not |
| `design` | Step 5 — find empty Design subsections, continue from the next one |
| `ready` | Step 6 — present plan for approval |
| `approved` | Step 7 — branch check, then dispatch |
| `implementing` | Step 8 — check if implementer finished, report results |

## Step 1 — Architecture check

Before any planning, ensure the codebase map is current:

- Run `git rev-parse HEAD` and read `.architecture-hash`.
- If `docs/codemonkeys/architecture.md` does not exist or the hash does not match HEAD:
  - Ask: "Architecture docs are missing/outdated — want me to update them first? This gives me a better map of the codebase before planning."
  - If yes: read and follow `project-architecture` to generate or update the architecture docs. Then continue to Step 2.
  - If no: continue to Step 2 without them.
- If the hash matches HEAD: continue silently to Step 2.

## Step 2 — Create plan file and explore context

Create the plan file immediately. It is the persistent state for the entire workflow — every decision, question, and answer gets written here so the workflow survives context compaction.

- If the user included a feature description with the command, use it. Otherwise ask: "What do you want to build?" and wait for a response.
- Generate plan filename: `docs/codemonkeys/plans/YYYY-MM-DD-<feature-slug>.md`
- Write the initial plan file (see Plan file format below).
- Read `docs/codemonkeys/architecture.md` if it exists.
- Read recent commits: `git log --oneline -10`
- Read relevant source files based on what the user described.
- Update the plan file: fill in the **Context** section with what you learned about the codebase and the user's intent. Set status to `exploring`.

## Step 3 — Clarifying questions

- Update plan status to `questions`.
- Ask one question at a time. Do NOT combine multiple questions into one message.
- Prefer multiple choice when possible, open-ended is fine too.
- Focus on: purpose, constraints, edge cases, acceptance criteria.
- **After each answer**: update the plan file — add the Q&A pair to the **Questions & Decisions** section. Mark unanswered questions as `*pending*`.
- Keep going until you have a clear picture of what to build.

## Step 4 — Propose 2-3 approaches

- Update plan status to `approaches`.
- Present approaches conversationally with tradeoffs.
- Lead with recommended option and explain why.
- Each approach should name: key files affected, main tradeoff, rough complexity.
- **After the user picks**: update the plan file — write all approaches to the **Approaches** section with the selected one marked.

## Step 5 — Present design

- Update plan status to `design`.
- Present section by section, scaled to complexity.
- Subsections: Architecture, Components & Files, Data Flow, Error Handling.
- Ask after each subsection: "Does this look right so far?"
- **After each subsection is confirmed**: update the plan file — write that subsection under **Design** and update **Acceptance Criteria**.
- Be ready to revise and go back. If the user changes their mind, update the plan file to reflect the change.

## Step 6 — Finalize and review plan

- Update plan status to `ready`.
- Rewrite the plan file into its final form. The finalized plan must include:
  - What we're building and why
  - Which files to create/modify and their responsibilities
  - Key design decisions and rationale
  - Expected behavior and acceptance criteria
- The plan describes *what* to build, not line-by-line code.
- Present: "Plan finalized at `docs/codemonkeys/plans/<filename>.md`. Please review and let me know if you want changes before I start implementation."
- Wait for explicit approval. Do NOT proceed until user says yes.
- If changes requested: update the plan, re-present, and ask again.

## Step 7 — Branch check

- Update plan status to `approved`.
- Run `git branch --show-current` to get the current branch.
- Check if it is a protected branch (main or master).
- If on a protected branch:
  - Suggest a branch name based on the feature name.
  - Ask: "You're on `<branch>` — want me to create `<suggested>` and switch to it?"
  - If yes: run `git checkout -b <branch-name>`.
  - If no: proceed (the user knows what they're doing).
- If already on a feature branch: proceed silently.

## Step 8 — Dispatch python-implementer

- Update plan status to `implementing`.
- Dispatch the `python-implementer` agent.
- Pass the plan file path as the prompt: "Implement the plan in `docs/codemonkeys/plans/<filename>.md`."
- The implementer reads the file and implements with TDD.
- Do NOT pass additional context — the plan file is the complete contract.

## Step 9 — Verify and format

After the implementer finishes:

1. Run `ruff check --fix .` and `ruff format .` on changed files. If ruff is not installed, skip and note it.
2. Run `pytest -x -q --tb=short --no-header` to verify all tests pass.
3. If tests fail, read the failure output and fix directly (smallest correct change). Maximum 2 fix cycles — if tests still fail after 2 attempts, report the remaining failures and move on.

## Step 10 — Report and clean up

- Update the plan file status to `complete`.
- Report:
  - Files created/modified
  - Tests pass/fail
  - Anything skipped and why

## Plan file format

Every plan file uses this structure. Write the entire file on each update — never patch individual lines.

```markdown
---
status: exploring
feature: <feature-name>
created: YYYY-MM-DD
---

## Context
<what the user wants to build and why>
<relevant codebase context>

## Questions & Decisions
### Q1: <question text>
**Answer**: <user's answer or *pending*>

## Approaches
### Option A — <name> (recommended)
<description, key files, tradeoffs>

### Option B — <name>
<description, key files, tradeoffs>

**Selected**: <which option and why>

## Design
### Architecture
<how it fits into the codebase>

### Components & Files
<files to create or modify, with responsibilities>

### Data Flow
<how data moves through the system>

### Error Handling
<error scenarios and how they're handled>

## Acceptance Criteria
- [ ] <criterion>
```

## Updating the plan file

- Write the entire file on every update. Do not patch individual sections.
- Always update the `status` field to reflect the current step.
- The plan file is the single source of truth. After compaction, trust the plan file over conversation memory.
- Sections that have not been reached yet should remain as empty headers (present but no content).

## Scaling to complexity

Not every feature needs 10 round trips. Scale the process to the size of the work:

- **Small** (1-2 files, clear requirements): Ask 1-2 targeted questions, skip the approaches step if there's one obvious path, present the design as a single block instead of section-by-section. Get to the plan fast.
- **Medium** (3-5 files, some design decisions): Ask a few questions, propose 2 approaches, present design in 2-3 chunks.
- **Large** (6+ files, architectural impact): Full process — thorough questions, 2-3 approaches with tradeoffs, section-by-section design review.

Use your judgment. The user can always ask for more detail or say "looks good, keep going." The goal is a good plan, not a thorough process.

## Cancellation

The user can cancel at any point by saying "cancel", "abort", "nevermind", or similar.

When cancelled:
- Update the plan file status to `cancelled`.
- Confirm: "Cancelled. Plan file kept at `<path>` for reference."

## Compaction recovery

After context compaction, the skill instructions may be compressed away. If this happens:

- The user can re-invoke `/python-feature` to trigger Step 0, which scans `docs/codemonkeys/plans/` and finds the active plan by its status.
- If you notice a plan reference in the conversation but don't have the skill instructions loaded, tell the user: "There's an active plan but I've lost the skill context — run `/python-feature` to resume."

## Rules

- Never write code before the user approves the plan.
- Always confirm before proceeding to the next phase.
- The plan file is the contract — the implementer gets no other context.
- One question at a time during clarification (but scale to complexity — small features need fewer questions).
- Update the plan file after every meaningful interaction.
- On compaction recovery, read the plan file first and trust it completely.
