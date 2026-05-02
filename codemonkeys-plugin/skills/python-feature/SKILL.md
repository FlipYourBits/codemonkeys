---
name: python-feature
description: "Design-to-implementation workflow for Python features. Clarifying questions, design approaches, plan document, then TDD implementation via python-implementer agent."
---

Read and follow `shared/engineering-mindset.md` and `shared/python-guidelines.md` before proceeding.

## Hard gate

Do NOT write any code or dispatch any agent until the user has approved the plan document. This applies to every feature regardless of perceived simplicity. No exceptions.

## Step 1 — Explore context

- Read `docs/architecture.md` if it exists.
- Read recent commits: `git log --oneline -10`
- Read relevant source files based on what the user describes.
- Understand the current architecture and patterns before asking questions.

## Step 2 — Clarifying questions

- Ask one question at a time.
- Prefer multiple choice when possible, open-ended is fine too.
- Focus on: purpose, constraints, edge cases, acceptance criteria.
- Keep going until you have a clear picture of what to build.
- Do NOT combine multiple questions into one message.

## Step 3 — Propose 2-3 approaches

- Present approaches conversationally with tradeoffs.
- Lead with recommended option and explain why.
- Each approach should name: key files affected, main tradeoff, rough complexity.

## Step 4 — Present design

- Present section by section, scaled to complexity.
- Sections: architecture, components/files, data flow, error handling, acceptance criteria.
- Ask after each section: "Does this look right so far?"
- Be ready to revise and go back.

## Step 5 — Write plan

- Save to `docs/plans/YYYY-MM-DD-<feature-name>.md`
- Contents:
  - What we're building and why
  - Which files to create/modify and their responsibilities
  - Key design decisions and rationale
  - Expected behavior / acceptance criteria
- The plan describes *what* to build, not line-by-line code.
- Commit the plan file.

## Step 6 — User reviews plan

- Present: "Plan written to `docs/plans/<filename>.md`. Please review and let me know if you want changes before I start implementation."
- Wait for explicit approval. Do NOT proceed until user says yes.
- If changes requested, update the plan, re-commit, and ask again.

## Step 7 — Dispatch python-implementer

- Dispatch the `python-implementer` agent.
- Pass the plan file path as the prompt: "Implement the plan in `docs/plans/<filename>.md`."
- The implementer reads the file and implements with TDD.
- Do NOT pass additional context — the plan file is the complete contract.

## Step 8 — Verify

After the implementer finishes, run verification inline:

- `python -m ruff check --fix .` then `python -m ruff format .`
- `python -m mypy .`
- `python -m pytest -x -q --tb=short --no-header`

## Step 9 — Fix if needed

- If verification fails, fix directly (smallest correct change).
- Run verification again.
- Max 2 cycles. If still failing, STOP and report what fails and why.

## Step 10 — Report

- Files created/modified
- Tests pass/fail
- Anything skipped and why

## Rules

- Never write code before the user approves the plan.
- Always confirm before proceeding to the next phase.
- The plan file is the contract — the implementer gets no other context.
- One question at a time during clarification.
