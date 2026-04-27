# Python Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone sequential pipeline that runs all quality checks (lint, format, test, coverage, code review, security audit, doc review, dependency audit, final lint) on existing code.

**Architecture:** Single graph file using `Pipeline` with conditional config based on `--mode` CLI arg. Sequential steps so each node can fix issues before the next runs.

**Tech Stack:** Python, LangGraph, langclaude Pipeline, argparse, asyncio

---

### Task 1: Write the graph module

**Files:**
- Create: `src/langclaude/graphs/python_quality_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_quality_gate_graph.py`:

```python
from __future__ import annotations

import pytest

from langclaude.graphs.python_quality_gate import build_pipeline
from langclaude.nodes.base import Verbosity


class TestBuildPipeline:
    def test_builds_with_full_mode(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p._app is not None
        assert p.working_dir == "/tmp/repo"

    def test_builds_with_diff_mode(self):
        p = build_pipeline("/tmp/repo", mode="diff", base_ref="develop")
        assert p._app is not None
        assert p.extra_state.get("base_ref") == "develop"

    def test_full_mode_no_config_overrides(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.config == {}

    def test_diff_mode_sets_config_overrides(self):
        p = build_pipeline("/tmp/repo", mode="diff")
        assert p.config.get("python_coverage") == {"mode": "diff"}
        assert p.config.get("code_review") == {"mode": "diff"}
        assert p.config.get("security_audit") == {"mode": "diff"}
        assert p.config.get("docs_review") == {"mode": "diff"}

    def test_diff_mode_default_base_ref(self):
        p = build_pipeline("/tmp/repo", mode="diff")
        assert p.extra_state.get("base_ref") == "main"

    def test_verbosity_passed_through(self):
        p = build_pipeline("/tmp/repo", mode="full", verbosity=Verbosity.verbose)
        assert p.verbosity == Verbosity.verbose

    def test_steps_are_correct_sequence(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.steps == [
            "python_lint",
            "python_format",
            "python_test",
            "python_coverage",
            "code_review",
            "security_audit",
            "docs_review",
            "dependency_audit",
            "python_lint",
        ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_quality_gate_graph.py -x -q --no-header`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write the implementation**

Create `src/langclaude/graphs/python_quality_gate.py`:

```python
"""Python code quality gate.

Sequential pipeline: lint, format, test, coverage, code review,
security audit, doc review, dependency audit, final lint.

Run with:

    python -m langclaude.graphs.python_quality_gate /path/to/repo
    python -m langclaude.graphs.python_quality_gate /path/to/repo --mode diff --base-ref main
"""

from __future__ import annotations

import argparse
import asyncio

from langclaude.nodes.base import Verbosity
from langclaude.pipeline import Pipeline


def build_pipeline(
    working_dir: str,
    *,
    mode: str = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    config: dict[str, dict[str, str]] = {}
    extra_state: dict[str, str] = {}

    if mode == "diff":
        for node in ("python_coverage", "code_review", "security_audit", "docs_review"):
            config[node] = {"mode": "diff"}
        extra_state["base_ref"] = base_ref

    return Pipeline(
        working_dir=working_dir,
        steps=[
            "python_lint",
            "python_format",
            "python_test",
            "python_coverage",
            "code_review",
            "security_audit",
            "docs_review",
            "dependency_audit",
            "python_lint",
        ],
        config=config,
        verbosity=verbosity,
        extra_state=extra_state,
    )


async def main(
    working_dir: str,
    mode: str = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(working_dir, mode=mode, base_ref=base_ref, verbosity=verbosity)
    final = await pipeline.run()

    print("\n=== Quality Gate Results ===")
    print(f"tests:    {str(final.get('python_test', '?'))[:200]}")
    print(f"coverage: {str(final.get('python_coverage', '?'))[:200]}")
    print(f"cost:     ${final.get('last_cost_usd', 0):.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Python quality gate pipeline.",
    )
    parser.add_argument("working_dir", help="Path to the repository root")
    parser.add_argument(
        "--mode",
        choices=["full", "diff"],
        default="full",
        help="Scan entire repo (full) or only changes vs base ref (diff). Default: full",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Git ref to diff against when --mode=diff (default: main)",
    )
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
        help="Output verbosity (default: normal)",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.working_dir,
            mode=args.mode,
            base_ref=args.base_ref,
            verbosity=Verbosity(args.verbosity),
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_quality_gate_graph.py -x -q --no-header`
Expected: All 7 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/langclaude/graphs/python_quality_gate.py tests/test_quality_gate_graph.py
git commit -m "feat: add python_quality_gate graph for standalone code quality checks"
```
