# Pipeline Context Passing, Cost Tracking, and Resolve Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `requires` config for inter-node context, per-node cost tracking, minimal status-line output, and a `resolve_findings` node that consolidates all review findings for interactive fixing.

**Architecture:** `_merge_wrap` in Pipeline gains responsibility for accumulating `node_outputs`, `node_costs`, and `total_cost_usd`. A new `_build_requires_context` method injects upstream output into state before each node runs. `ClaudeAgentNode._render_prompt` auto-prepends `_prior_results`. Review nodes lose Edit/Write and their feedback loops. A new `resolve_findings` node receives all findings and fixes interactively.

**Tech Stack:** Python, LangGraph, langclaude Pipeline, claude_agent_sdk

---

### Task 1: Cost tracking in `_merge_wrap`

**Files:**
- Modify: `src/langclaude/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
class TestCostTracking:
    def test_node_costs_accumulated(self):
        costs = []

        async def step_a(state):
            costs.append("a")
            return {"a": "done", "last_cost_usd": 0.05}

        async def step_b(state):
            costs.append("b")
            return {"b": "done", "last_cost_usd": 0.10}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["node_costs"] == {"a": 0.05, "b": 0.10}
        assert final["total_cost_usd"] == pytest.approx(0.15)
        assert "last_cost_usd" not in final

    def test_node_costs_zero_for_no_cost_node(self):
        async def step_a(state):
            return {"a": "done"}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["node_costs"] == {"a": 0.0}
        assert final["total_cost_usd"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py::TestCostTracking -x -q --no-header`
Expected: FAIL (no `node_costs` key in state)

- [ ] **Step 3: Implement cost tracking in `_merge_wrap`**

Replace `_merge_wrap` in `src/langclaude/pipeline.py`:

```python
def _make_tracking_wrap(self, graph_name: str, node: Any) -> Any:
    """Wrap a node to merge state, track costs, and accumulate outputs."""
    if Pipeline._is_async(node):

        async def _wrapper(state):
            result = await node(state)
            if not isinstance(result, dict):
                return result
            cost = result.pop("last_cost_usd", 0.0)
            node_costs = {**state.get("node_costs", {}), graph_name: cost}
            total_cost = state.get("total_cost_usd", 0.0) + cost
            node_outputs = {**state.get("node_outputs", {})}
            if graph_name in result:
                node_outputs[graph_name] = result[graph_name]
            return {
                **state,
                **result,
                "node_costs": node_costs,
                "total_cost_usd": total_cost,
                "node_outputs": node_outputs,
            }

        return _wrapper

    def _wrapper(state):
        result = node(state)
        if not isinstance(result, dict):
            return result
        cost = result.pop("last_cost_usd", 0.0)
        node_costs = {**state.get("node_costs", {}), graph_name: cost}
        total_cost = state.get("total_cost_usd", 0.0) + cost
        node_outputs = {**state.get("node_outputs", {})}
        if graph_name in result:
            node_outputs[graph_name] = result[graph_name]
        return {
            **state,
            **result,
            "node_costs": node_costs,
            "total_cost_usd": total_cost,
            "node_outputs": node_outputs,
        }

    return _wrapper
```

Update `_instantiate` and `_resolve_step` to call `self._make_tracking_wrap(graph_name, node)` instead of `self._merge_wrap(node)`.

Remove the old `_merge_wrap` static method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/langclaude/pipeline.py tests/test_pipeline.py
git commit -m "feat: add per-node cost tracking and node_outputs accumulator"
```

---

### Task 2: Requires config and `_prior_results` injection

**Files:**
- Modify: `src/langclaude/pipeline.py`
- Modify: `src/langclaude/nodes/base.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
class TestRequiresConfig:
    def test_prior_results_injected(self):
        async def step_a(state):
            return {"a": '{"findings": []}', "last_cost_usd": 0.0}

        async def step_b(state):
            assert "_prior_results" in state
            assert "### a" in state["_prior_results"]
            assert '{"findings": []}' in state["_prior_results"]
            return {"b": "saw context", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
            config={"b": {"requires": ["a"]}},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["b"] == "saw context"

    def test_no_requires_no_prior_results(self):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.0}

        async def step_b(state):
            assert "_prior_results" not in state or state["_prior_results"] == ""
            return {"b": "no context", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a", "custom/b"],
            custom_nodes={"custom/a": step_a, "custom/b": step_b},
        )
        final = asyncio.get_event_loop().run_until_complete(p.run())
        assert final["b"] == "no context"

    def test_requires_invalid_node_raises(self):
        async def step_a(state):
            return {"a": "done"}

        with pytest.raises(ValueError, match="requires.*nonexistent"):
            Pipeline(
                working_dir="/tmp",
                task="test",
                steps=["custom/a"],
                custom_nodes={"custom/a": step_a},
                config={"a": {"requires": ["nonexistent"]}},
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py::TestRequiresConfig -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Implement requires injection**

In `src/langclaude/pipeline.py`, add a `_requires_map` built during `_build()` that maps graph_name → list of required node names. Add validation that required names appear earlier in the step list.

Update `_make_tracking_wrap` to inject `_prior_results` into state before calling the node:

```python
def _make_tracking_wrap(self, graph_name: str, node: Any) -> Any:
    requires = self._requires_map.get(graph_name, [])

    if Pipeline._is_async(node):

        async def _wrapper(state):
            if requires:
                node_outputs = state.get("node_outputs", {})
                parts = ["## Prior results\n"]
                for req in requires:
                    output = node_outputs.get(req, "")
                    parts.append(f"### {req}\n{output}\n")
                state = {**state, "_prior_results": "\n".join(parts)}
            result = await node(state)
            if not isinstance(result, dict):
                return result
            cost = result.pop("last_cost_usd", 0.0)
            node_costs = {**state.get("node_costs", {}), graph_name: cost}
            total_cost = state.get("total_cost_usd", 0.0) + cost
            node_outputs_new = {**state.get("node_outputs", {})}
            if graph_name in result:
                node_outputs_new[graph_name] = result[graph_name]
            return {
                **state,
                **result,
                "node_costs": node_costs,
                "total_cost_usd": total_cost,
                "node_outputs": node_outputs_new,
            }

        return _wrapper

    # ... sync version same pattern ...
```

Add `_validate_requires` called from `_build()`:

```python
def _validate_requires(self, ordered_names: list[str]) -> None:
    self._requires_map: dict[str, list[str]] = {}
    for name in ordered_names:
        node_config = self.config.get(name, {})
        requires = node_config.get("requires", [])
        if not requires:
            continue
        for req in requires:
            if req not in ordered_names or ordered_names.index(req) >= ordered_names.index(name):
                raise ValueError(
                    f"requires: node {name!r} requires {req!r} but it "
                    f"does not appear earlier in the step list"
                )
        self._requires_map[name] = requires
```

- [ ] **Step 4: Auto-prepend `_prior_results` in `ClaudeAgentNode._render_prompt`**

In `src/langclaude/nodes/base.py`, modify `_render_prompt`:

```python
def _render_prompt(self, state: dict[str, Any]) -> str:
    try:
        prompt = self.prompt_template.format(**state)
    except KeyError as e:
        raise KeyError(
            f"node {self.name!r} prompt_template references missing state key: {e.args[0]!r}"
        ) from e
    prior = state.get("_prior_results", "")
    if prior:
        return f"{prior}\n\n{prompt}"
    return prompt
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: All pass

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/langclaude/pipeline.py src/langclaude/nodes/base.py tests/test_pipeline.py
git commit -m "feat: add requires config for inter-node context passing"
```

---

### Task 3: Status-line output in Pipeline

**Files:**
- Modify: `src/langclaude/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
class TestStatusLine:
    def test_normal_verbosity_prints_status(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.03}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.normal,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        err = capsys.readouterr().err
        assert "a" in err
        assert "done" in err

    def test_silent_verbosity_no_output(self, capsys):
        async def step_a(state):
            return {"a": "done", "last_cost_usd": 0.0}

        p = Pipeline(
            working_dir="/tmp",
            task="test",
            steps=["custom/a"],
            custom_nodes={"custom/a": step_a},
            verbosity=Verbosity.silent,
        )
        asyncio.get_event_loop().run_until_complete(p.run())
        err = capsys.readouterr().err
        assert err == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py::TestStatusLine -x -q --no-header`
Expected: FAIL

- [ ] **Step 3: Implement status-line printing**

In `_make_tracking_wrap`, add timing and status output. The wrapper prints to stderr:

```python
import sys
import time

# In the async wrapper, before and after calling node:
if self.verbosity != Verbosity.silent:
    print(f"● {graph_name}...", end="", file=sys.stderr, flush=True)
    t0 = time.time()

result = await node(state)

if self.verbosity != Verbosity.silent:
    elapsed = time.time() - t0
    cost = result.get("last_cost_usd", 0.0) if isinstance(result, dict) else 0.0
    cost_str = f", ${cost:.4f}" if cost > 0 else ""
    print(f" done ({elapsed:.1f}s{cost_str})", file=sys.stderr)
```

When `verbosity=Verbosity.normal`, nodes run with `Verbosity.silent` (no per-message streaming). When `verbosity=Verbosity.verbose`, nodes keep their own verbosity for full streaming AND the status line prints.

Update `_apply_overrides` to force `verbosity=Verbosity.silent` on nodes when pipeline verbosity is `normal`:

```python
if "verbosity" in params and "verbosity" not in overrides:
    if self.verbosity == Verbosity.normal:
        overrides["verbosity"] = Verbosity.silent
    else:
        overrides["verbosity"] = self.verbosity
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -x -q --no-header`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/langclaude/pipeline.py tests/test_pipeline.py
git commit -m "feat: add status-line output for pipeline nodes"
```

---

### Task 4: Make review nodes report-only

**Files:**
- Modify: `src/langclaude/nodes/code_review.py`
- Modify: `src/langclaude/nodes/security_audit.py`
- Modify: `src/langclaude/nodes/docs_review.py`
- Test: `tests/test_review_selfcontained.py`

- [ ] **Step 1: Simplify `code_review_node` — remove feedback loop, remove Edit/Write**

Replace the entire function body of `code_review_node` in `src/langclaude/nodes/code_review.py`:

```python
_ALLOW = [
    "Read", "Glob", "Grep",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]


def code_review_node(
    *,
    name: str = "code_review",
    mode: Mode = "diff",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    **kwargs: Any,
) -> ClaudeAgentNode:
    if mode == "diff":
        prompt_template = (
            "DIFF mode — review only changes introduced by the diff "
            "against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        prompt_template = (
            "FULL mode — review the entire repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT + SKILL,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
```

Remove the `ask_review_feedback_via_stdin` function, `AskFeedback` type, and related imports (`asyncio`, `sys`).

Update `_SYSTEM_PROMPT` to remove "fix each issue" — change to:
```python
_SYSTEM_PROMPT = (
    "You are a senior engineer conducting a semantic code review. "
    "Read the code directly — do not run linters, formatters, type-checkers, "
    "or tests (other pipeline nodes handle those). "
    "Follow the skill below. Report findings only — do not fix issues. "
    "Output JSON only as your final message."
)
```

- [ ] **Step 2: Simplify `security_audit_node` — same pattern**

Replace `security_audit_node` in `src/langclaude/nodes/security_audit.py` to return a plain `ClaudeAgentNode` (same pattern as code_review above). Remove feedback loop, Edit/Write from allow, and fix-related language from system prompt.

```python
_ALLOW = [
    "Read", "Glob", "Grep",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]


def security_audit_node(
    *,
    name: str = "security_audit",
    mode: Mode = "diff",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    **kwargs: Any,
) -> ClaudeAgentNode:
    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only vulnerabilities introduced by the "
            "diff against {base_ref}. Start by running `git diff {base_ref}...HEAD` "
            "and reading the changed files."
        )
    else:
        prompt_template = (
            "FULL mode — audit the repository at {working_dir}. "
            "Start by listing files and reading the code."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT + SKILL,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else [],
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
```

Update `_SYSTEM_PROMPT`:
```python
_SYSTEM_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Read the code directly — trace data flow from inputs to sinks. "
    "Follow the skill below. Report findings only — do not fix issues. "
    "Output JSON only as your final message."
)
```

Remove `ask_audit_feedback_via_stdin`, `AskFeedback`, and related imports.

- [ ] **Step 3: Remove Edit/Write from `docs_review_node`**

In `src/langclaude/nodes/docs_review.py`, update `_ALLOW`:

```python
_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
]
```

Update `_SYSTEM_PROMPT` to remove fix language:
```python
_SYSTEM_PROMPT = (
    "You are reviewing docs for drift against the code they describe. "
    "Use Bash/Read to examine git diff, changed files, and doc files "
    "(README, CHANGELOG, etc.). Follow the skill below exactly. "
    "Report findings only — do not fix issues. "
    "Do not run tests, linters, or install packages — only read code and docs. "
    "Output JSON only as your final message."
)
```

Remove the `_DENY` list (no longer needed since Edit/Write are gone and only git Bash is allowed).

- [ ] **Step 4: Update tests**

Update `tests/test_review_selfcontained.py` to remove tests that depend on `ask_feedback` parameter or Edit/Write permissions. Verify the simplified nodes construct without error.

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass (some tests may need updating if they reference removed params)

- [ ] **Step 6: Commit**

```bash
git add src/langclaude/nodes/code_review.py src/langclaude/nodes/security_audit.py src/langclaude/nodes/docs_review.py tests/
git commit -m "refactor: make review nodes report-only (no Edit/Write, no feedback loops)"
```

---

### Task 5: Create `resolve_findings` node

**Files:**
- Create: `src/langclaude/nodes/resolve_findings.py`
- Modify: `src/langclaude/registry.py`
- Modify: `src/langclaude/nodes/__init__.py`
- Test: `tests/test_resolve_findings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolve_findings.py`:

```python
from __future__ import annotations

from langclaude.nodes.resolve_findings import resolve_findings_node
from langclaude.nodes.base import ClaudeAgentNode


class TestResolveFindings:
    def test_constructs_with_defaults(self):
        node = resolve_findings_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "resolve_findings"

    def test_allow_includes_edit_write(self):
        node = resolve_findings_node()
        assert "Edit" in node.allow
        assert "Write" in node.allow

    def test_deny_includes_pip_install(self):
        node = resolve_findings_node()
        assert any("pip install" in d for d in node.deny)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_resolve_findings.py -x -q --no-header`
Expected: FAIL with ImportError

- [ ] **Step 3: Create `resolve_findings_node`**

Create `src/langclaude/nodes/resolve_findings.py`:

```python
"""Resolve-findings node: interactive issue fixer.

Receives JSON findings from upstream review nodes via _prior_results,
presents a summary to the user, and fixes selected issues.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langclaude.nodes.base import ClaudeAgentNode, Verbosity
from langclaude.permissions import UnmatchedPolicy

_SYSTEM_PROMPT = (
    "You are a senior engineer fixing issues found by code review. "
    "You will receive JSON findings from prior review nodes. "
    "Present a numbered summary of all findings to the user, grouped by "
    "severity (HIGH first, then MEDIUM, then LOW). Ask the user which "
    "issues to fix: all, specific numbers, a category, or none. "
    "Then fix the selected issues — make the smallest correct change per "
    "issue, verify by re-reading the file. Run tests after fixing to "
    "ensure no regressions. Do not push. "
    "Output JSON only as your final message — a summary of what was fixed."
)

_ALLOW = [
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git blame*)",
    "Bash(git status*)",
    "Bash(git ls-files*)",
    "Bash(python -m pytest*)",
    "Bash(python -m unittest*)",
]

_DENY = [
    "Bash(pip install*)",
    "Bash(pip uninstall*)",
    "Bash(python -m pip*)",
]


def resolve_findings_node(
    *,
    name: str = "resolve_findings",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    max_turns: int | None = None,
    verbosity: Verbosity = Verbosity.silent,
    **kwargs: Any,
) -> ClaudeAgentNode:
    return ClaudeAgentNode(
        name=name,
        system_prompt=_SYSTEM_PROMPT,
        skills=[*extra_skills],
        allow=list(allow) if allow is not None else _ALLOW,
        deny=list(deny) if deny is not None else _DENY,
        on_unmatched=on_unmatched,
        prompt_template="Review the findings above and ask the user which to fix.",
        max_turns=max_turns,
        verbosity=verbosity,
        **kwargs,
    )
```

- [ ] **Step 4: Register the node**

In `src/langclaude/registry.py`, add to `_register_builtins`:

```python
from langclaude.nodes.resolve_findings import resolve_findings_node

_BUILTINS["resolve_findings"] = resolve_findings_node
```

In `src/langclaude/nodes/__init__.py`, add:

```python
from langclaude.nodes.resolve_findings import resolve_findings_node
```

And add `"resolve_findings_node"` to `__all__`.

Update `tests/test_registry.py` to include `"resolve_findings"` in the expected builtins set.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_resolve_findings.py tests/test_registry.py -x -q --no-header`
Expected: All pass

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/langclaude/nodes/resolve_findings.py src/langclaude/registry.py src/langclaude/nodes/__init__.py tests/test_resolve_findings.py tests/test_registry.py
git commit -m "feat: add resolve_findings node for interactive issue fixing"
```

---

### Task 6: Update quality gate graph

**Files:**
- Modify: `src/langclaude/graphs/python_quality_gate.py`
- Modify: `tests/test_quality_gate_graph.py`

- [ ] **Step 1: Update `build_pipeline` with requires and resolve_findings**

```python
def build_pipeline(
    working_dir: str,
    *,
    mode: Mode = "diff",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    config: dict[str, dict[str, Any]] = {}
    extra_state: dict[str, str] = {"base_ref": base_ref}

    if mode == "diff":
        for node in ("python_coverage", "code_review", "security_audit", "docs_review"):
            config[node] = {"mode": "diff"}

    config["resolve_findings"] = {
        "requires": [
            "code_review",
            "security_audit",
            "docs_review",
            "python_dependency_audit",
        ],
    }
    config["python_lint_2"] = {"requires": ["python_lint"]}

    return Pipeline(
        working_dir=working_dir,
        steps=[
            "python_lint",
            "python_format",
            "python_coverage",
            "python_test",
            "python_dependency_audit",
            "code_review",
            "security_audit",
            "docs_review",
            "resolve_findings",
            "python_lint",
        ],
        config=config,
        verbosity=verbosity,
        extra_state=extra_state,
    )
```

- [ ] **Step 2: Update `main()` to print cost table**

```python
async def main(
    working_dir: str,
    mode: str = "full",
    base_ref: str = "main",
    verbosity: Verbosity = Verbosity.normal,
) -> None:
    pipeline = build_pipeline(
        working_dir, mode=mode, base_ref=base_ref, verbosity=verbosity
    )
    final = await pipeline.run()

    print("\n=== Quality Gate Results ===")
    node_costs = final.get("node_costs", {})
    for name, cost in node_costs.items():
        print(f"{name:<25}${cost:.4f}")
    print("─" * 33)
    print(f"{'total':<25}${final.get('total_cost_usd', 0):.4f}")
```

- [ ] **Step 3: Update tests**

In `tests/test_quality_gate_graph.py`, update the step sequence test:

```python
    def test_steps_are_correct_sequence(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert p.steps == [
            "python_lint",
            "python_format",
            "python_coverage",
            "python_test",
            "python_dependency_audit",
            "code_review",
            "security_audit",
            "docs_review",
            "resolve_findings",
            "python_lint",
        ]
```

Add test for requires config:

```python
    def test_resolve_findings_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "resolve_findings" in p.config
        assert p.config["resolve_findings"]["requires"] == [
            "code_review",
            "security_audit",
            "docs_review",
            "python_dependency_audit",
        ]

    def test_python_lint_2_has_requires(self):
        p = build_pipeline("/tmp/repo", mode="full")
        assert "python_lint_2" in p.config
        assert p.config["python_lint_2"]["requires"] == ["python_lint"]
```

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --no-header`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/langclaude/graphs/python_quality_gate.py tests/test_quality_gate_graph.py
git commit -m "feat: wire resolve_findings and requires config into quality gate"
```
