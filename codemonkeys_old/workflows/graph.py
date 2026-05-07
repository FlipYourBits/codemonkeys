"""Generate interactive HTML workflow graph visualization.

After a workflow run completes, inspects the Workflow definition and
WorkflowContext.phase_results to produce a self-contained HTML file
with a dagre-based DAG visualization. Open in any browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codemonkeys.workflows._graph_html import _HTML_TEMPLATE
from codemonkeys.workflows.phases import PhaseType, Workflow, WorkflowContext

_PHASE_CATEGORIES: dict[str, str] = {
    "discover": "subprocess",
    "mechanical_audit": "subprocess",
    "verify": "subprocess",
}


def _categorize_phase(name: str, phase_type: PhaseType) -> str:
    if phase_type == PhaseType.GATE:
        return "gate"
    return _PHASE_CATEGORIES.get(name, "agent")


def _summarize_value(key: str, value: Any) -> str:
    """Produce a short human-readable label for a phase output value."""
    if isinstance(value, list):
        return f"{len(value)} {key}"
    if hasattr(value, "findings") and isinstance(getattr(value, "findings"), list):
        return f"{len(value.findings)} findings"
    if hasattr(value, "ruff"):
        parts = []
        for attr in ("ruff", "pyright", "secrets", "pip_audit", "dead_code"):
            v = getattr(value, attr, None)
            if isinstance(v, list) and v:
                parts.append(f"{len(v)} {attr}")
        if hasattr(value, "pytest") and value.pytest:
            parts.append(f"{value.pytest.passed}p/{value.pytest.failed}f")
        return ", ".join(parts) if parts else key
    if isinstance(value, str) and len(value) > 100:
        return f"{key} ({len(value)} chars)"
    if value is None:
        return ""
    return key


def _build_edge_label(phase_result: dict[str, Any] | None) -> str:
    """Build a compact edge label from a phase's output dict."""
    if not phase_result or not isinstance(phase_result, dict):
        return ""
    parts = [_summarize_value(k, v) for k, v in phase_result.items()]
    return ", ".join(p for p in parts if p)


def _describe_value(key: str, value: Any) -> dict[str, Any]:
    """Produce a detailed description of a phase output value for the detail panel."""
    if value is None:
        return {"key": key, "type": "null", "summary": "None"}
    if isinstance(value, list):
        items_preview: list[str] = []
        for item in value[:10]:
            if isinstance(item, str):
                items_preview.append(item)
            elif hasattr(item, "file"):
                items_preview.append(getattr(item, "file", str(item)))
            elif hasattr(item, "title"):
                items_preview.append(getattr(item, "title", str(item)))
            else:
                items_preview.append(repr(item)[:60])
        return {
            "key": key,
            "type": f"list[{len(value)}]",
            "summary": f"{len(value)} items",
            "items": items_preview,
            "truncated": len(value) > 10,
        }
    if isinstance(value, str):
        return {
            "key": key,
            "type": "str",
            "summary": f"{len(value)} chars",
            "preview": value[:200] + ("..." if len(value) > 200 else ""),
        }
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        summary_parts = []
        for k, v in dumped.items():
            if isinstance(v, list):
                summary_parts.append(f"{k}: {len(v)} items")
            elif v is not None:
                summary_parts.append(f"{k}: {repr(v)[:40]}")
        return {
            "key": key,
            "type": type(value).__name__,
            "summary": ", ".join(summary_parts[:5]),
            "fields": {k: repr(v)[:100] for k, v in dumped.items()},
        }
    if isinstance(value, dict):
        return {
            "key": key,
            "type": "dict",
            "summary": f"{len(value)} keys",
            "fields": {k: repr(v)[:100] for k, v in list(value.items())[:10]},
        }
    return {"key": key, "type": type(value).__name__, "summary": repr(value)[:100]}


def _build_graph_data(workflow: Workflow, context: WorkflowContext) -> dict[str, Any]:
    """Build the JSON data structure for the graph visualization."""
    nodes = []
    edges = []

    for phase in workflow.phases:
        result = context.phase_results.get(phase.name)
        output_detail = []
        if result and isinstance(result, dict):
            for k, v in result.items():
                output_detail.append(_describe_value(k, v))

        nodes.append(
            {
                "id": phase.name,
                "label": phase.name.replace("_", " "),
                "category": _categorize_phase(phase.name, phase.phase_type),
                "output": output_detail,
            }
        )

    for i, phase in enumerate(workflow.phases[:-1]):
        next_phase = workflow.phases[i + 1]
        result = context.phase_results.get(phase.name)
        label = _build_edge_label(result)
        edges.append(
            {
                "from": phase.name,
                "to": next_phase.name,
                "label": label,
            }
        )

    return {
        "workflow": workflow.name,
        "run_id": context.run_id,
        "nodes": nodes,
        "edges": edges,
    }


def generate_workflow_graph(
    workflow: Workflow,
    context: WorkflowContext,
    output_dir: Path | None = None,
) -> Path:
    """Generate an interactive HTML graph of the completed workflow run.

    Returns the path to the generated HTML file.
    """
    graph_data = _build_graph_data(workflow, context)

    if output_dir is None:
        output_dir = Path(context.cwd) / ".codemonkeys" / context.run_id

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "workflow_graph.html"

    html = _HTML_TEMPLATE.format(
        workflow_name=workflow.name,
        run_id=context.run_id,
        graph_json=json.dumps(graph_data, indent=2),
    )
    output_path.write_text(html)
    return output_path
