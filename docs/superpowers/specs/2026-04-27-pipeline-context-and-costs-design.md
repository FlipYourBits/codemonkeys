# Pipeline Context Passing, Cost Tracking, and Issue Fixer

## Problem

1. Nodes run in isolation — downstream nodes can't see upstream findings
2. Cost reporting only shows the last node's cost
3. Verbose stdout from every node wastes tokens and clutters output
4. Interactive feedback loops in review nodes are awkward — they fix then ask if you want to fix

## Solution

Five changes:

1. **`requires` config** — nodes declare which upstream outputs they need
2. **`node_outputs` accumulator** — stores each node's output in state
3. **Per-node cost tracking** — `node_costs` dict + `total_cost_usd` sum
4. **Minimal stdout** — nodes run silently; pipeline prints a one-line status per node
5. **Issue fixer node** — review nodes become report-only; a final interactive node presents all findings and fixes what the user selects

## 1. Requires Config

Pipeline config gains a `requires` key per node — a list of upstream node names whose output should be injected into this node's prompt.

```python
Pipeline(
    steps=["python_lint", "code_review", "python_lint"],
    config={
        "python_lint_2": {"requires": ["python_lint", "code_review"]},
    },
)
```

Before `python_lint_2` runs, the pipeline builds a context block from the required nodes' stored outputs and injects it into state as `_prior_results`. The node's prompt is then prepended with this context.

### Injection format

```
## Prior results

### python_lint
<output from python_lint node>

### code_review
<output from code_review node>
```

### Injection mechanism

`ClaudeAgentNode._render_prompt` checks for `state["_prior_results"]`. If present and non-empty, it prepends it to the rendered prompt with a blank line separator. Nodes don't need to add `{_prior_results}` to their templates — it's automatic.

ShellNodes don't receive prior results (they run fixed commands).

### Missing requires

If a required node hasn't run yet (typo, wrong ordering), the pipeline raises `ValueError` at build time by validating that each `requires` entry names a step that appears earlier in the sequence.

## 2. Node Outputs Accumulator

`state["node_outputs"]` is a `dict[str, str]` that grows after each node completes.

- After `_merge_wrap` applies, the pipeline stores `state[node_name]` into `state["node_outputs"][node_name]`
- This happens in `_merge_wrap` itself — it reads the node's declared output key and copies it

This means `node_outputs` is always available for the `requires` injection to read from.

## 3. Cost Tracking

### State keys

- `state["node_costs"]`: `dict[str, float]` — maps each node's graph name to its cost in USD
- `state["total_cost_usd"]`: `float` — running sum of all node costs

### Accumulation

`_merge_wrap` handles this:
1. After the node returns, read `result.get("last_cost_usd", 0.0)`
2. Store it in `state["node_costs"][graph_name]`
3. Add it to `state["total_cost_usd"]`
4. Remove `last_cost_usd` from the merged state (it's now in `node_costs`)

ShellNodes don't return `last_cost_usd`, so they get `0.0`.

### End-of-run summary

Graph `main()` functions print a cost table:

```
=== Quality Gate Results ===
python_lint          $0.0000
python_format        $0.0000
python_coverage      $0.0842
python_test          $0.1203
code_review          $0.0956
security_audit       $0.0734
docs_review          $0.0612
python_dep_audit     $0.0445
python_lint_2        $0.0000
─────────────────────────────
total                $0.4792
```

## 4. Minimal Stdout

Replace per-message streaming output with a single status line per node:

```
● python_lint... done (0.2s)
● python_format... done (0.1s)
● python_coverage... done (12.4s, $0.0842)
● code_review... done (18.1s, $0.0956)
```

Implementation:
- Pipeline's `_merge_wrap` prints the status line (node name, elapsed time, cost if >0)
- Nodes run with `verbosity=silent` internally — no per-message streaming
- The Pipeline accepts a `verbosity` that controls whether these status lines print (normal = status lines, silent = nothing, verbose = full streaming as today)

This saves tokens because the agent's text output isn't streamed to stdout and parsed — it just goes into state.

## 5. Issue Fixer Node

### Review nodes become report-only

Remove `Edit`/`Write` from review node allow lists. Remove the interactive `ask_feedback` loop. They analyze and return JSON findings — that's it.

Affected nodes:
- `code_review` — remove Edit/Write from allow, remove ask_feedback loop, return JSON directly
- `security_audit` — same
- `docs_review` — already doesn't have the loop, just remove Edit/Write

### New node: `resolve_findings`

A new interactive `ClaudeAgentNode` that:
1. Receives all findings via `requires` (code_review, security_audit, docs_review, python_dependency_audit)
2. Presents a summary to the user: N findings across M categories
3. Asks what to fix (all, specific categories, specific findings, or none)
4. Fixes the selected issues
5. Returns JSON summary of what was fixed

```python
def resolve_findings_node(
    *,
    name: str = "resolve_findings",
    ...
) -> Callable:
```

**Allow list:** Read, Glob, Grep, Edit, Write, Bash(git*), Bash(python -m pytest*) — it needs Edit/Write to make fixes and can run tests to verify.

**Pipeline position:** After all review nodes, before final lint.

### Updated quality gate steps

```python
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
config={
    "resolve_findings": {
        "requires": ["code_review", "security_audit", "docs_review", "python_dependency_audit"],
    },
    "python_lint_2": {
        "requires": ["python_lint"],
    },
},
```

## Files Changed

- `src/langclaude/pipeline.py` — `_merge_wrap` accumulates `node_outputs`, `node_costs`, `total_cost_usd`, prints status lines; `_inject_requires` builds `_prior_results`; validation of `requires` at build time
- `src/langclaude/nodes/base.py` — `ClaudeAgentNode._render_prompt` auto-prepends `_prior_results` if present
- `src/langclaude/nodes/code_review.py` — remove Edit/Write from allow, remove ask_feedback loop, return JSON directly from ClaudeAgentNode
- `src/langclaude/nodes/security_audit.py` — same
- `src/langclaude/nodes/docs_review.py` — remove Edit/Write from allow
- `src/langclaude/nodes/resolve_findings.py` — new node
- `src/langclaude/graphs/python_quality_gate.py` — add requires config, resolve_findings step, cost table output, status-line verbosity
- `src/langclaude/graphs/python_new_feature.py` — cost table output
- `src/langclaude/registry.py` — register resolve_findings
- `src/langclaude/nodes/__init__.py` — export resolve_findings

## Non-goals

- No structured output enforcement beyond system prompts (nodes already return JSON)
- No truncation of stored outputs (revisit if token usage becomes a problem)
- No changes to ShellNode interface
- The `python_new_feature` graph keeps its current interactive flow for now (it uses review nodes differently)
