---
name: project-architecture
description: "Builds and maintains docs/architecture.md — a comprehensive project snapshot. Checks commit hash for freshness, updates incrementally or from scratch."
---

Read and follow `shared/engineering-mindset.md` and `shared/python-guidelines.md` before proceeding.

## Step 1 — Check freshness

- Run `git rev-parse HEAD` to get the current commit SHA.
- Read `.architecture-hash` in the repo root.
- If the file exists and the hash matches HEAD: respond "Architecture docs are up to date." and **stop**.
- If the file does not exist: proceed to Step 3 (first run).
- If the hash differs from HEAD: proceed to Step 2 (incremental update).

## Step 2 — Incremental update

- Run `git diff <stored_hash>..HEAD` to see what changed since the last update.
- Read the current `docs/architecture.md`.
- Read the changed files to understand them in context.
- Rewrite `docs/architecture.md` in full incorporating the changes — do not patch individual sections, rewrite the whole document.
- Proceed to Step 4.

## Step 3 — First run (from scratch)

- Run `git ls-files` to discover all tracked source files.
- Read source files to understand the project structure, purpose, and patterns.
- Write `docs/architecture.md` from scratch following the document sections below.
- Proceed to Step 4.

## Step 4 — Write hash

- Write the HEAD SHA to `.architecture-hash` (repo root, single line, no trailing content).

## Document sections (all required)

Every version of `docs/architecture.md` must contain exactly these five sections:

### 1. Project Overview

- What the project is, what problem it solves, who it is for.
- Tech stack and key dependencies.
- How to install and run.

### 2. Architecture

- Module-level map: what each top-level directory and package does.
- Inter-module dependencies.
- Key data flows.

### 3. File Index

- One line per source file: `path — what it does`.
- Grouped by directory.

### 4. Key Abstractions

- Core concepts and how they relate.
- Use concrete names from the code (class names, function names, constants).

### 5. Conventions

- Patterns the codebase follows.
- How to extend the project (where to add new modules, how to register them).

## Rules

- Never modify source code — only write to `docs/` and `.architecture-hash`.
- Describe what IS, not what SHOULD BE. No recommendations.
- Keep `docs/architecture.md` under 500 lines.
- Only analyze files tracked by git. Skip `.venv/`, `node_modules/`, etc.
