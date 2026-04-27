# Pipeline, Registry & Self-Contained Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every node a single self-contained Claude agent session (runs tool, analyzes, optionally fixes — all in one `query()` call), controlled by permissions not special params. Then layer a Pipeline + Registry system so graphs are built from string step lists.

**Architecture:** Each node's behavior is driven by three levers: (1) system prompt — what to do, (2) allow/deny — what tools it can use, (3) `on_unmatched` — auto-approve vs interactive. No special `fix` parameter. Review nodes gain read-write capability by changing their allow list. Deterministic py_ nodes that need fixing become Claude nodes. A module-level registry maps strings to factory callables. `Pipeline` resolves steps from the registry, injects config/skills, and builds a `StateGraph`.

**Tech Stack:** Python 3.10+, LangGraph, Claude Agent SDK, existing `langclaude` primitives.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/langclaude/nodes/code_review.py` | Merge review + fix into one agent session via allow/deny |
| Modify | `src/langclaude/nodes/security_audit.py` | Same pattern |
| Modify | `src/langclaude/nodes/docs_review.py` | Same pattern |
| Modify | `src/langclaude/nodes/test_runner.py` | Become Claude node (single session: run pytest, analyze, fix) |
| Modify | `src/langclaude/nodes/test_coverage.py` | Become Claude node (single session: run coverage, analyze, add tests) |
| Modify | `src/langclaude/nodes/dependency_audit.py` | Become Claude node (single session: run scanners, analyze, upgrade) |
| Delete | `src/langclaude/nodes/issue_fixer.py` | Absorbed — each node fixes its own findings |
| Delete | `src/langclaude/nodes/bug_fixer.py` | Absorbed — pytest node fixes its own failures |
| Create | `src/langclaude/registry.py` | Built-in + user registries, `register()`, `resolve()` |
| Create | `src/langclaude/pipeline.py` | `Pipeline` class |
| Modify | `src/langclaude/__init__.py` | Update exports |
| Modify | `src/langclaude/graphs/python_new_feature.py` | Rewrite with Pipeline |
| Modify | `src/langclaude/graphs/python_full_repo_review.py` | Rewrite with Pipeline |
| Modify | `README.md` | Document new API |
| Create | `tests/test_registry.py` | Registry tests |
| Create | `tests/test_pipeline.py` | Pipeline tests |

---

### Task 1: Make review nodes self-contained (single Claude session)

Currently review nodes deny Edit/Write and are read-only. The change: make allow/deny configurable so that when Edit/Write are allowed, the system prompt tells Claude to also fix issues it finds. One `query()` call, one agent session.

**Files:**
- Modify: `src/langclaude/nodes/code_review.py`
- Modify: `src/langclaude/nodes/security_audit.py`
- Modify: `src/langclaude/nodes/docs_review.py`

- [ ] **Step 1: Write failing test for code_review with write permissions**

```python
# tests/test_review_selfcontained.py
from __future__ import annotations

import pytest

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.nodes.code_review import claude_code_review_node


class TestCodeReviewSelfContained:
    def test_default_is_readonly(self):
        node = claude_code_review_node()
        assert isinstance(node, ClaudeAgentNode)
        assert "Edit" in node.deny
        assert "Write" in node.deny

    def test_allow_edit_write_removes_from_deny(self):
        node = claude_code_review_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)", "Bash(git commit*)"],
        )
        assert isinstance(node, ClaudeAgentNode)
        assert "Edit" not in node.deny
        assert "Write" not in node.deny

    def test_system_prompt_includes_fix_when_write_allowed(self):
        node = claude_code_review_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)"],
        )
        assert "fix" in node.system_prompt.lower() or "edit" in node.system_prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_review_selfcontained.py -x -q --no-header`
Expected: FAIL — `node.deny` check fails since Edit/Write are always in _DEFAULT_DENY.

- [ ] **Step 3: Update code_review.py**

The key change: detect whether Edit/Write are in the allow list. If so, append fix instructions to the system prompt. The node stays a plain `ClaudeAgentNode` — no wrapper, no two-phase.

```python
# src/langclaude/nodes/code_review.py
"""Code-review node: Claude agent that gathers context and reviews code.

Claude runs linters, diffs, and type-checkers itself via Bash, then
performs semantic review and triage following the code-review skill.

When Edit/Write are in the allow list (and not denied), the agent also
fixes issues it finds. Control interactive vs auto approval via
on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_REVIEW_ONLY_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the code-review skill. "
    "Do not edit files; do not push. "
    "Output JSON only as your final message."
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior engineer conducting a code review. "
    "Use Bash to run git diff, linters (ruff, mypy, pyright, eslint, tsc, "
    "etc.), and type-checkers — only run tools that are installed. "
    "Then perform semantic review and triage following the code-review skill. "
    "After reviewing, fix each issue you found — make the smallest correct "
    "change per issue, verify by re-reading the file. Do not push. "
    "Output JSON only as your final message."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)

_READWRITE_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash", "Edit", "Write")

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    run_tests: bool = False,
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "review_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a code-review node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    Control interactive approval via on_unmatched:
        - "allow": auto-approve all tool calls (CI / auto mode)
        - "deny": deny unmatched tools
        - ask_via_stdin: prompt per tool call (interactive mode)

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``review_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

    test_instruction = (
        "Also run the project's test suite and include failures in your review. "
        if run_tests
        else "Do not run tests. "
    )

    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {%s}. Start by running `git diff {%s}...HEAD` and "
            "any available linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % (base_ref_key, base_ref_key, test_instruction)
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and running any available "
            "linters/type-checkers. %s"
            "Then proceed to semantic review and triage."
        ) % test_instruction

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=["code-review", *extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_review_selfcontained.py -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Apply same pattern to security_audit.py**

Same structure: `_REVIEW_ONLY_PROMPT` vs `_REVIEW_AND_FIX_PROMPT`, `_READONLY_ALLOW`/`_READONLY_DENY` vs `_READWRITE_ALLOW`/`_READWRITE_DENY`, detect via `_has_write_tools()`. The security-specific prompts:

```python
_REVIEW_ONLY_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "security-audit skill. Do not edit files; do not push. "
    "Output JSON only as your final message."
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "security-audit skill. After reviewing, fix each vulnerability you "
    "found — make the smallest correct change per issue, verify by "
    "re-reading the file. Do not push. "
    "Output JSON only as your final message."
)
```

Signature change: `deny: Sequence[str] | None = None` (was `Sequence[str] = _DEFAULT_DENY`). Same auto-detection logic.

- [ ] **Step 6: Apply same pattern to docs_review.py**

Same structure. Docs-specific prompts:

```python
_REVIEW_ONLY_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the docs-review skill exactly. "
    "Do not edit files; do not push. Output JSON only as your final message."
)

_REVIEW_AND_FIX_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the docs-review skill exactly. "
    "After reviewing, update any docs that have drifted — fix factual "
    "errors, update outdated examples, add missing sections. Do not push. "
    "Output JSON only as your final message."
)
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/langclaude/nodes/code_review.py src/langclaude/nodes/security_audit.py src/langclaude/nodes/docs_review.py tests/test_review_selfcontained.py
git commit -m "feat: make review nodes self-contained — single session, fix controlled by allow/deny"
```

---

### Task 2: Convert deterministic nodes to self-contained Claude nodes

The pytest, coverage, and dep audit nodes currently run CLI tools deterministically. Convert them to Claude nodes that run the tool, analyze output, and optionally fix — all in one session. The allow/deny list controls whether they can edit.

**Files:**
- Modify: `src/langclaude/nodes/test_runner.py`
- Modify: `src/langclaude/nodes/test_coverage.py`
- Modify: `src/langclaude/nodes/dependency_audit.py`

- [ ] **Step 1: Write failing test for pytest as Claude node**

```python
# tests/test_runner_claude.py
from __future__ import annotations

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.nodes.test_runner import claude_pytest_node


class TestPytestClaudeNode:
    def test_returns_claude_agent_node(self):
        node = claude_pytest_node()
        assert isinstance(node, ClaudeAgentNode)

    def test_default_is_readonly(self):
        node = claude_pytest_node()
        assert "Edit" in node.deny

    def test_readwrite_when_edit_allowed(self):
        node = claude_pytest_node(
            allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
            deny=["Bash(git push*)"],
        )
        assert "Edit" not in node.deny
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_runner_claude.py -x -q --no-header`
Expected: FAIL — `claude_pytest_node` doesn't exist.

- [ ] **Step 3: Rewrite test_runner.py as a Claude node**

Replace the deterministic `py_pytest_runner_node` with `claude_pytest_node`. The Claude agent runs pytest via Bash, reads failures, and (if Edit/Write allowed) fixes them. Single session.

```python
# src/langclaude/nodes/test_runner.py
"""Pytest node: Claude agent that runs the test suite, analyzes failures,
and optionally fixes them — all in one session.

When Edit/Write are denied (default), the agent runs pytest and reports
findings. When allowed, it also diagnoses and fixes failing tests.
Control interactive approval via on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_READONLY_PROMPT = (
    "You are a senior engineer running the project's test suite. "
    "Use Bash to run pytest (or the project's test runner). "
    "Analyze any failures: read the failing test and the code under test "
    "to identify the root cause. "
    "Do not edit files. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, and recommendation."
)

_READWRITE_PROMPT = (
    "You are a senior engineer running the project's test suite. "
    "Use Bash to run pytest (or the project's test runner). "
    "Analyze any failures: read the failing test and the code under test "
    "to identify the root cause. Then fix the underlying bug — do not "
    "weaken assertions or delete tests. Make the smallest correct change. "
    "Re-run the tests to verify your fix. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you fixed it."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)

_READWRITE_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash", "Edit", "Write")

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_pytest_node(
    *,
    name: str = "pytest",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "test_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a pytest node.

    By default read-only: runs tests and reports failures. To enable
    fixing, pass Edit/Write in the allow list.

    State input:
        working_dir: repo root.

    State output:
        ``output_key``: findings JSON.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _READWRITE_PROMPT if can_fix else _READONLY_PROMPT

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template="Run the test suite in {working_dir} and analyze any failures.",
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_runner_claude.py -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Rewrite test_coverage.py as a Claude node**

```python
# src/langclaude/nodes/test_coverage.py
"""Coverage node: Claude agent that runs coverage analysis and optionally
adds tests for uncovered code — all in one session.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_READONLY_PROMPT = (
    "You are a senior engineer analyzing test coverage. "
    "Use Bash to run `pytest --cov` (or the project's coverage tool). "
    "Identify uncovered lines and branches. "
    "Do not edit files. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, and recommendation."
)

_READWRITE_PROMPT = (
    "You are a senior engineer analyzing test coverage. "
    "Use Bash to run `pytest --cov` (or the project's coverage tool). "
    "Identify uncovered lines and branches. Then write tests to cover "
    "the most important gaps — focus on business logic and error paths. "
    "Re-run coverage to verify improvement. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category, description, recommendation, and "
    "whether you added a test."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit", "Write",
    "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)",
)

_READWRITE_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash", "Edit", "Write")

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)", "Bash(rm*)",
    "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_coverage_node(
    *,
    name: str = "coverage",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "coverage_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a coverage node.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key``: findings JSON.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _READWRITE_PROMPT if can_fix else _READONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — analyze coverage only for files changed since "
            "{%s}. Run `pytest --cov` in {working_dir}."
        ) % base_ref_key
    else:
        prompt_template = (
            "FULL mode — analyze coverage for the entire repo at "
            "{working_dir}. Run `pytest --cov`."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
```

- [ ] **Step 6: Rewrite dependency_audit.py as a Claude node**

```python
# src/langclaude/nodes/dependency_audit.py
"""Dependency-audit node: Claude agent that runs SCA scanners and
optionally upgrades vulnerable dependencies — all in one session.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

_READONLY_PROMPT = (
    "You are auditing project dependencies for known vulnerabilities. "
    "Use Bash to run whichever SCA tools are installed: pip-audit, "
    "npm audit, govulncheck, cargo audit, bundler-audit. Only run "
    "tools that are installed and relevant to the project's ecosystem. "
    "Do not edit files. Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category (vulnerable_dependency), source, "
    "description, recommendation, and confidence."
)

_READWRITE_PROMPT = (
    "You are auditing project dependencies for known vulnerabilities. "
    "Use Bash to run whichever SCA tools are installed: pip-audit, "
    "npm audit, govulncheck, cargo audit, bundler-audit. Only run "
    "tools that are installed and relevant to the project's ecosystem. "
    "After identifying vulnerabilities, upgrade affected dependencies "
    "to patched versions. Verify the upgrade doesn't break tests. "
    "Do not push. "
    "Output JSON only as your final message — a list of findings with "
    "file, line, severity, category (vulnerable_dependency), source, "
    "description, recommendation, confidence, and whether you fixed it."
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit", "Write",
    "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)",
)

_READWRITE_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash", "Edit", "Write")

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)", "Bash(rm*)",
    "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_dependency_audit_node(
    *,
    name: str = "dependency_audit",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "dep_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a dependency-audit node.

    State input:
        working_dir: repo root.

    State output:
        ``output_key``: findings JSON.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(_READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY)

    can_fix = _has_write_tools(allow_list)
    system_prompt = _READWRITE_PROMPT if can_fix else _READONLY_PROMPT

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template="Audit dependencies in {working_dir} for known vulnerabilities.",
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: PASS (some existing tests may need updating — see Step 8).

- [ ] **Step 8: Fix broken tests from rename**

Update any tests that imported the old names:
- `py_pytest_runner_node` → `claude_pytest_node`
- `py_pytest_coverage_node` → `claude_coverage_node`
- `py_dependency_audit_node` → `claude_dependency_audit_node`

Files to check: `tests/test_validation.py`, `tests/test_dep_audit_parsers.py`.

In `tests/test_validation.py`, update imports:
```python
from langclaude import (
    OutputKeyConflict,
    claude_code_review_node,
    claude_security_audit_node,
    claude_dependency_audit_node,
    claude_pytest_node,
    claude_coverage_node,
    claude_issue_fixer_node,   # remove in Task 3
    validate_node_outputs,
)
```

Replace usages:
- `py_dependency_audit_node()` → `claude_dependency_audit_node()`
- `py_pytest_coverage_node()` → `claude_coverage_node()`
- `py_pytest_runner_node()` → `claude_pytest_node()`

In `tests/test_dep_audit_parsers.py`, the parsers (`_pip_audit`, `_npm_audit`, etc.) are now gone since the node is a Claude agent. These tests test deterministic parsing logic that no longer exists — delete the file.

- [ ] **Step 9: Run all tests again**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/langclaude/nodes/test_runner.py src/langclaude/nodes/test_coverage.py src/langclaude/nodes/dependency_audit.py tests/
git commit -m "feat: convert pytest, coverage, dep audit to self-contained Claude nodes"
```

---

### Task 3: Remove issue_fixer and bug_fixer

Their functionality is absorbed — each node fixes its own findings when Edit/Write are allowed.

**Files:**
- Delete: `src/langclaude/nodes/issue_fixer.py`
- Delete: `src/langclaude/nodes/bug_fixer.py`
- Modify: `src/langclaude/__init__.py`
- Modify: `src/langclaude/nodes/__init__.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Delete the files**

```bash
rm src/langclaude/nodes/issue_fixer.py src/langclaude/nodes/bug_fixer.py
```

- [ ] **Step 2: Update `src/langclaude/__init__.py`**

Remove:
```python
from langclaude.nodes.bug_fixer import claude_bug_fixer_node
from langclaude.nodes.issue_fixer import (
    ask_finding_via_stdin,
    claude_issue_fixer_node,
)
```

Remove from `__all__`:
```python
"ask_finding_via_stdin",
"claude_bug_fixer_node",
"claude_issue_fixer_node",
```

Update imports to use new node names:
```python
from langclaude.nodes.test_runner import claude_pytest_node
from langclaude.nodes.test_coverage import claude_coverage_node
from langclaude.nodes.dependency_audit import claude_dependency_audit_node
```

Update `__all__` entries:
- `"py_pytest_runner_node"` → `"claude_pytest_node"`
- `"py_pytest_coverage_node"` → `"claude_coverage_node"`
- `"py_dependency_audit_node"` → `"claude_dependency_audit_node"`

- [ ] **Step 3: Update `src/langclaude/nodes/__init__.py`**

Remove `claude_bug_fixer_node` import. Update other renamed imports.

- [ ] **Step 4: Update test_validation.py**

Remove `claude_issue_fixer_node` and `claude_bug_fixer_node` imports and test cases. Update remaining tests to use new names.

- [ ] **Step 5: Delete `src/langclaude/fixer.py` if it was created, and `tests/test_fixer.py`**

The shared fixer module is no longer needed since we dropped the two-phase approach.

- [ ] **Step 6: Also delete `src/langclaude/findings.py` and `tests/test_findings.py`**

The findings parsing module was used by the old issue_fixer two-phase approach. With single-session Claude nodes, Claude handles its own output — no need for external parsing. Check if anything else imports it first:

```bash
grep -r "from langclaude.findings" src/ tests/ --include="*.py"
```

If nothing remains, delete. If the graphs or __init__.py still import it, remove those imports too.

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -u
git commit -m "refactor: remove issue_fixer, bug_fixer, and findings parser (absorbed into self-contained nodes)"
```

---

### Task 4: Registry module

**Files:**
- Create: `src/langclaude/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry.py
from __future__ import annotations

import pytest

from langclaude.registry import (
    list_builtins,
    list_registered,
    register,
    resolve,
)


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from langclaude import registry as reg
    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


class TestBuiltins:
    def test_known_builtins_exist(self):
        builtins = list_builtins()
        expected = {
            "new_branch",
            "implement_feature",
            "code_review",
            "security_audit",
            "docs_review",
            "ruff_fix",
            "ruff_fmt",
            "pytest",
            "coverage",
            "dependency_audit",
        }
        assert expected == set(builtins)

    def test_resolve_builtin(self):
        factory = resolve("ruff_fix")
        assert callable(factory)

    def test_resolve_unknown_raises(self):
        with pytest.raises(KeyError, match="no_such_node"):
            resolve("no_such_node")


class TestUserRegistry:
    def test_register_and_resolve(self):
        async def my_node(state):
            return {}

        register("deploy", my_node, namespace="acme")
        resolved = resolve("acme/deploy")
        assert resolved is my_node

    def test_register_default_namespace(self):
        async def my_node(state):
            return {}

        register("lint", my_node)
        resolved = resolve("custom/lint")
        assert resolved is my_node

    def test_register_name_with_slash_raises(self):
        with pytest.raises(ValueError, match="must not contain"):
            register("bad/name", lambda s: {})

    def test_resolve_unknown_user_node_raises(self):
        with pytest.raises(KeyError, match="not found in user registry"):
            resolve("custom/nonexistent")

    def test_list_registered(self):
        register("alpha", lambda s: {}, namespace="test")
        register("beta", lambda s: {}, namespace="test")
        registered = list_registered()
        assert "test/alpha" in registered
        assert "test/beta" in registered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_registry.py -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Write the registry module**

```python
# src/langclaude/registry.py
"""Node registry: maps string names to node factory callables.

Built-in nodes are bare strings (no slash). User-registered nodes require
a namespace prefix (e.g. "custom/my_node", "acme/deploy"). Resolution:
no "/" -> built-in lookup; has "/" -> user registry lookup.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_BUILTINS: dict[str, Callable[..., Any]] = {}
_USER_REGISTRY: dict[str, Callable[..., Any]] = {}


def _register_builtins() -> None:
    from langclaude.nodes.branch_namer import claude_new_branch_node
    from langclaude.nodes.code_review import claude_code_review_node
    from langclaude.nodes.dependency_audit import claude_dependency_audit_node
    from langclaude.nodes.docs_review import claude_docs_review_node
    from langclaude.nodes.feature_implementer import claude_feature_implementer_node
    from langclaude.nodes.ruff_node import shell_ruff_fix_node, shell_ruff_fmt_node
    from langclaude.nodes.security_audit import claude_security_audit_node
    from langclaude.nodes.test_coverage import claude_coverage_node
    from langclaude.nodes.test_runner import claude_pytest_node

    _BUILTINS.update({
        "new_branch": claude_new_branch_node,
        "implement_feature": claude_feature_implementer_node,
        "code_review": claude_code_review_node,
        "security_audit": claude_security_audit_node,
        "docs_review": claude_docs_review_node,
        "ruff_fix": shell_ruff_fix_node,
        "ruff_fmt": shell_ruff_fmt_node,
        "pytest": claude_pytest_node,
        "coverage": claude_coverage_node,
        "dependency_audit": claude_dependency_audit_node,
    })


def _ensure_builtins() -> None:
    if not _BUILTINS:
        _register_builtins()


def register(
    name: str,
    node: Callable[..., Any],
    *,
    namespace: str = "custom",
) -> None:
    """Register a user-defined node under namespace/name."""
    if "/" in name:
        raise ValueError(
            f"name must not contain '/': {name!r}. "
            f"Pass the namespace separately via namespace="
        )
    _USER_REGISTRY[f"{namespace}/{name}"] = node


def resolve(name: str) -> Callable[..., Any]:
    """Look up a node by registry name.

    Bare names (no "/") resolve from built-ins. Namespaced names
    resolve from the user registry. Raises KeyError if not found.
    """
    if "/" in name:
        if name not in _USER_REGISTRY:
            raise KeyError(
                f"{name!r} not found in user registry. "
                f"Registered: {sorted(_USER_REGISTRY)}"
            )
        return _USER_REGISTRY[name]

    _ensure_builtins()
    if name not in _BUILTINS:
        raise KeyError(
            f"{name!r} not found in built-in registry. "
            f"Available: {sorted(_BUILTINS)}"
        )
    return _BUILTINS[name]


def list_builtins() -> list[str]:
    """Return sorted list of built-in node names."""
    _ensure_builtins()
    return sorted(_BUILTINS)


def list_registered() -> list[str]:
    """Return sorted list of user-registered node names."""
    return sorted(_USER_REGISTRY)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_registry.py -x -q --no-header`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/langclaude/registry.py tests/test_registry.py
git commit -m "feat: add node registry with built-in and user-namespaced lookups"
```

---

### Task 5: Pipeline class

**Files:**
- Create: `src/langclaude/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline.py
from __future__ import annotations

import asyncio

import pytest

from langclaude.pipeline import Pipeline


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from langclaude import registry as reg
    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


class TestPipelineConstruction:
    def test_creates_with_string_steps(self):
        p = Pipeline(
            working_dir="/tmp/repo",
            task="add healthz",
            steps=["ruff_fix", "ruff_fmt"],
        )
        assert p.working_dir == "/tmp/repo"

    def test_rejects_empty_steps(self):
        with pytest.raises(ValueError, match="steps"):
            Pipeline(working_dir="/tmp", task="x", steps=[])

    def test_unknown_step_raises(self):
        with pytest.raises(KeyError, match="nonexistent"):
            Pipeline(working_dir="/tmp", task="x", steps=["nonexistent"])

    def test_parallel_steps(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=[["ruff_fix", "ruff_fmt"]],
        )
        assert p._app is not None

    def test_config_overrides(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["ruff_fix"],
            config={"ruff_fix": {"fix": False}},
        )
        assert p._app is not None

    def test_aliased_tuple_step(self):
        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["ruff_fix", ("ruff_final", "ruff_fix")],
            config={"ruff_final": {"name": "ruff_final", "output_key": "ruff_final_output"}},
        )
        assert p._app is not None


class TestPipelineCustomNodes:
    def test_custom_node_inline(self):
        async def my_node(state):
            return {"out": "ok"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/deploy"],
            custom_nodes={"custom/deploy": my_node},
        )
        assert p._app is not None

    def test_run_with_custom_nodes(self):
        calls = []

        async def step_a(state):
            calls.append("a")
            return {"a_out": "done"}

        async def step_b(state):
            calls.append("b")
            return {"b_out": "done"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert calls == ["a", "b"]
        assert final.get("a_out") == "done"


class TestPublicAPI:
    def test_importable_from_langclaude(self):
        from langclaude import Pipeline, register, list_builtins, list_registered, resolve
        assert Pipeline is not None
        assert callable(register)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Write the Pipeline class**

```python
# src/langclaude/pipeline.py
"""High-level Pipeline: build a LangGraph workflow from string step names.

Steps are resolved from the node registry. Lists within `steps` create
parallel fan-out (same semantics as `chain()`).
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Union

from langgraph.graph import StateGraph

from langclaude.graphs import chain
from langclaude.registry import register, resolve

Step = Union[str, tuple[str, str]]


class Pipeline:
    """Build and run a LangGraph workflow from registry node names.

    Args:
        working_dir: repo root passed into state as "working_dir".
        task: task description passed into state as "task_description".
        steps: list of node name strings, (graph_name, registry_key) tuples,
            or nested lists for parallel fan-out.
        extra_skills: skill names injected into every node whose factory
            accepts an `extra_skills` parameter.
        config: per-node overrides keyed by step name or graph_name.
        custom_nodes: dict mapping namespaced names to node callables.
            Registered before resolution. Inline alternative to register().
        verbose: default verbose flag for nodes that accept it.
        extra_state: additional key-value pairs merged into initial state.
    """

    def __init__(
        self,
        *,
        working_dir: str,
        task: str = "",
        steps: Sequence[Any],
        extra_skills: Sequence[str | Path] = (),
        config: dict[str, dict[str, Any]] | None = None,
        custom_nodes: dict[str, Any] | None = None,
        verbose: bool = False,
        extra_state: dict[str, Any] | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        self.working_dir = working_dir
        self.task = task
        self.steps = list(steps)
        self.extra_skills = list(extra_skills)
        self.config = dict(config or {})
        self.custom_nodes = dict(custom_nodes or {})
        self.verbose = verbose
        self.extra_state = dict(extra_state or {})

        self._register_custom_nodes()
        self._app = self._build()

    def _register_custom_nodes(self) -> None:
        for key, node in self.custom_nodes.items():
            factory = (lambda _n=node, **kw: _n) if callable(node) else node
            if "/" not in key:
                register(key, factory, namespace="custom")
            else:
                ns, _, name = key.rpartition("/")
                register(name, factory, namespace=ns)

    def _apply_overrides(self, factory: Any, overrides: dict[str, Any]) -> Any:
        sig = inspect.signature(factory)
        params = sig.parameters

        if "extra_skills" in params and self.extra_skills:
            existing = list(overrides.get("extra_skills", ()))
            merged = list(dict.fromkeys([*self.extra_skills, *existing]))
            overrides["extra_skills"] = merged

        if "verbose" in params and "verbose" not in overrides:
            overrides["verbose"] = self.verbose

        if overrides:
            return factory(**overrides)
        return factory()

    def _instantiate(self, name: str) -> tuple[str, Any]:
        factory = resolve(name)
        graph_name = name.rsplit("/", 1)[-1]
        overrides = dict(self.config.get(name, {}))
        node = self._apply_overrides(factory, overrides)
        return graph_name, node

    def _resolve_step(self, step: Any) -> Any:
        if isinstance(step, list):
            return [self._resolve_step(s) for s in step]
        if isinstance(step, tuple):
            graph_name, registry_key = step
            factory = resolve(registry_key)
            overrides = dict(self.config.get(registry_key, {}))
            overrides.update(self.config.get(graph_name, {}))
            node = self._apply_overrides(factory, overrides)
            return graph_name, node
        return self._instantiate(step)

    def _build(self) -> Any:
        graph = StateGraph(dict)
        resolved = [self._resolve_step(s) for s in self.steps]
        chain(graph, *resolved)
        return graph.compile()

    async def run(self, **extra: Any) -> dict[str, Any]:
        state: dict[str, Any] = {
            "working_dir": self.working_dir,
            "task_description": self.task,
            **self.extra_state,
            **extra,
        }
        return await self._app.ainvoke(state)
```

- [ ] **Step 4: Update `src/langclaude/__init__.py` exports**

Add:
```python
from langclaude.pipeline import Pipeline
from langclaude.registry import list_builtins, list_registered, register, resolve
```

Add to `__all__`:
```python
"Pipeline", "list_builtins", "list_registered", "register", "resolve",
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/langclaude/pipeline.py src/langclaude/__init__.py tests/test_pipeline.py
git commit -m "feat: add Pipeline class with step resolution, config injection, and custom_nodes"
```

---

### Task 6: Rewrite pre-built graphs to use Pipeline

**Files:**
- Modify: `src/langclaude/graphs/python_new_feature.py`
- Modify: `src/langclaude/graphs/python_full_repo_review.py`

- [ ] **Step 1: Rewrite python_new_feature.py**

```python
# src/langclaude/graphs/python_new_feature.py
"""Python feature implementation workflow.

End-to-end graph: creates a branch, implements, lints, runs all review
nodes in parallel (each self-contained with fixing enabled), final lint,
and commits.

Run with:

    python -m langclaude.graphs.python_new_feature /path/to/repo "add a retry decorator"
"""

from __future__ import annotations

import asyncio
import shlex
import sys

from langclaude.nodes.base import ShellNode
from langclaude.pipeline import Pipeline


def _commit_node(**kwargs) -> ShellNode:
    return ShellNode(
        name="commit",
        command=lambda s: [
            "bash", "-c",
            "git add -A && git commit -m "
            + shlex.quote(f"feat: {s.get('task_description', 'implement feature')}")
        ],
        output_key="last_result",
        check=True,
    )


def build_pipeline(
    working_dir: str,
    task: str,
    *,
    base_ref: str = "main",
    verbose: bool = True,
) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        task=task,
        steps=[
            "new_branch",
            "implement_feature",
            "ruff_fix",
            "ruff_fmt",
            [
                "pytest",
                "coverage",
                "code_review",
                "security_audit",
                "docs_review",
                "dependency_audit",
            ],
            ("ruff_final", "ruff_fix"),
            "custom/commit",
        ],
        extra_skills=["python-clean-code"],
        config={
            "pytest": {
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "coverage": {
                "mode": "diff", "base_ref_key": "base_ref",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "code_review": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "security_audit": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "docs_review": {
                "mode": "diff",
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "dependency_audit": {
                "allow": ["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
                "deny": ["Bash(rm -rf*)", "Bash(rm*)", "Bash(git push*)", "Bash(git commit*)", "Bash(git reset*)"],
            },
            "ruff_final": {"name": "ruff_final", "output_key": "ruff_final_output"},
        },
        custom_nodes={"custom/commit": _commit_node},
        verbose=verbose,
        extra_state={"base_ref": base_ref},
    )


async def main(working_dir: str, task: str, base_ref: str = "main") -> None:
    pipeline = build_pipeline(working_dir, task, base_ref=base_ref)
    final = await pipeline.run()

    print("\n=== Results ===")
    print(f"branch:   {final.get('branch_name', '?')}")
    print(f"tests:    {final.get('test_findings', '?')[:200]}")
    print(f"coverage: {final.get('coverage_findings', '?')[:200]}")
    print(f"cost:     ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "usage: python -m langclaude.graphs.python_new_feature "
            '<working_dir> "task description" [base_ref]',
            file=sys.stderr,
        )
        sys.exit(2)
    cwd = sys.argv[1]
    task_desc = sys.argv[2]
    base = sys.argv[3] if len(sys.argv) >= 4 else "main"
    asyncio.run(main(cwd, task_desc, base))
```

- [ ] **Step 2: Rewrite python_full_repo_review.py**

```python
# src/langclaude/graphs/python_full_repo_review.py
"""Full Python repository review workflow.

Runs all review nodes in parallel against the entire repo. Read-only
(default allow/deny) — no edits.

Run with:

    python -m langclaude.graphs.python_full_repo_review /path/to/repo
"""

from __future__ import annotations

import asyncio
import sys

from langclaude.pipeline import Pipeline


def build_pipeline(working_dir: str, *, verbose: bool = True) -> Pipeline:
    return Pipeline(
        working_dir=working_dir,
        steps=[
            [
                "ruff_fix",
                ["pytest", "coverage"],
                "code_review",
                "security_audit",
                "docs_review",
                "dependency_audit",
            ],
        ],
        config={
            "ruff_fix": {"fix": False, "fail_on_findings": False},
            "coverage": {"mode": "full"},
            "code_review": {"mode": "full"},
            "security_audit": {"mode": "full"},
            "docs_review": {"mode": "full"},
        },
        verbose=verbose,
    )


async def main(working_dir: str) -> None:
    pipeline = build_pipeline(working_dir)
    final = await pipeline.run()

    print("\n=== Full Repo Review ===")
    print(f"tests:      {str(final.get('test_findings', '<none>'))[:200]}")
    print(f"coverage:   {str(final.get('coverage_findings', '<none>'))[:200]}")
    print(f"dep vulns:  {str(final.get('dep_findings', '<none>'))[:200]}")
    print(f"review:     {str(final.get('review_findings', '<none>'))[:200]}")
    print(f"security:   {str(final.get('security_findings', '<none>'))[:200]}")
    print(f"docs:       {str(final.get('docs_findings', '<none>'))[:200]}")
    print(f"cost:       ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python -m langclaude.graphs.python_full_repo_review <working_dir>",
            file=sys.stderr,
        )
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/langclaude/graphs/python_new_feature.py src/langclaude/graphs/python_full_repo_review.py
git commit -m "refactor: rewrite pre-built graphs to use Pipeline with self-contained nodes"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README**

Key changes:
- Quick start uses `Pipeline`
- Node table: all nodes are now `claude_` prefixed except ruff (still `shell_`). New column showing read-only vs read-write behavior.
- Remove `issue_fixer` and `bug_fixer` from docs
- New "Pipeline" section: steps, config, custom_nodes, extra_skills
- New "Registry" section: register(), list_builtins()
- "Permissions control behavior" section explaining the allow/deny + on_unmatched pattern
- Keep raw chain() as "Manual wiring" subsection

Updated node table:

| Factory | Registry name | Default output key | Description |
|---|---|---|---|
| `claude_new_branch_node()` | `new_branch` | `branch_name` | Generates branch name, handles dirty tree, creates branch |
| `claude_feature_implementer_node()` | `implement_feature` | `last_result` | Implements feature from task_description |
| `claude_code_review_node()` | `code_review` | `review_findings` | Runs linters + semantic review. Allow Edit/Write to also fix. |
| `claude_security_audit_node()` | `security_audit` | `security_findings` | Runs security scanners + review. Allow Edit/Write to also fix. |
| `claude_docs_review_node()` | `docs_review` | `docs_findings` | Checks docs for drift. Allow Edit/Write to also fix. |
| `claude_pytest_node()` | `pytest` | `test_findings` | Runs pytest, analyzes failures. Allow Edit/Write to also fix. |
| `claude_coverage_node()` | `coverage` | `coverage_findings` | Runs coverage, finds gaps. Allow Edit/Write to add tests. |
| `claude_dependency_audit_node()` | `dependency_audit` | `dep_findings` | Runs SCA scanners. Allow Edit/Write to upgrade deps. |
| `shell_ruff_fix_node()` | `ruff_fix` | `ruff_fix_output` | Runs ruff check --fix |
| `shell_ruff_fmt_node()` | `ruff_fmt` | `ruff_fmt_output` | Runs ruff format |

Permissions section:
```markdown
## Permissions control behavior

Each node's behavior is controlled by three levers:

1. **allow/deny** — what tools the agent can use. Default: read-only. Pass Edit/Write to enable fixing.
2. **on_unmatched** — what happens for unmatched tool calls:
   - `"allow"`: auto-approve (CI / fully automatic)
   - `"deny"`: refuse (default)
   - `ask_via_stdin`: prompt the user (interactive)
3. **System prompt** — adjusts automatically based on permissions. Read-only nodes report findings; read-write nodes also fix them.

```python
# Report only (default):
claude_security_audit_node()

# Fix automatically:
claude_security_audit_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
)

# Fix with user approval per edit:
from langclaude import ask_via_stdin
claude_security_audit_node(
    allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"],
    deny=["Bash(git push*)"],
    on_unmatched=ask_via_stdin,
)
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for Pipeline, registry, and permission-driven behavior"
```

---

### Task 8: Lint and final validation

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: all pass

- [ ] **Step 2: Run ruff**

Run: `.venv/bin/python -m ruff check src/ tests/ && .venv/bin/python -m ruff format --check src/ tests/`
Expected: clean

- [ ] **Step 3: Commit lint fixes if needed**

```bash
git add -A
git commit -m "style: fix lint issues"
```
