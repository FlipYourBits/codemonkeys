---
name: AgentRunner consolidation in progress
description: run_review.py being refactored into thin CLI layer; AgentRunner absorbing the shared logic (parallel dispatch, progress display, etc.)
type: project
---

run_review.py is being refactored in a separate session. The good parts (parallel agent dispatch, progress display, structured output parsing) are being moved into AgentRunner as the consolidated location. run_review.py becomes a thin CLI layer on top.

**Why:** AgentRunner should be the single place for agent execution logic; run_review was accumulating too much orchestration that belongs in the runner.

**How to apply:** New workflows (like deep-clean) should depend on AgentRunner's capabilities, not on patterns currently in run_review.py. The deep-clean workflow spec should be implemented against the AgentRunner API, not by duplicating run_review patterns. Wait for the refactor to land before implementing deep-clean if there are API conflicts.
