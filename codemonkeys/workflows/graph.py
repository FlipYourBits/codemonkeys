"""Generate interactive HTML workflow graph visualization.

After a workflow run completes, inspects the Workflow definition and
WorkflowContext.phase_results to produce a self-contained HTML file
with a dagre-based DAG visualization. Open in any browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _build_graph_data(workflow: Workflow, context: WorkflowContext) -> dict[str, Any]:
    """Build the JSON data structure for the graph visualization."""
    nodes = []
    edges = []

    for phase in workflow.phases:
        nodes.append(
            {
                "id": phase.name,
                "label": phase.name.replace("_", " "),
                "category": _categorize_phase(phase.name, phase.phase_type),
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


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Workflow: {workflow_name} — {run_id}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1b26; color: #c0caf5; padding: 20px; }}
h1 {{ font-size: 1.2rem; margin-bottom: 16px; color: #7aa2f7; }}
.meta {{ font-size: 0.85rem; color: #565f89; margin-bottom: 24px; }}
#graph-container {{ width: 100%; height: calc(100vh - 100px); overflow: auto; }}
svg {{ display: block; margin: 0 auto; }}
.node rect {{ stroke-width: 2px; rx: 8; ry: 8; }}
.node.subprocess rect {{ fill: #1e2030; stroke: #7dcfff; }}
.node.agent rect {{ fill: #1e2030; stroke: #bb9af7; }}
.node.gate rect {{ fill: #1e2030; stroke: #e0af68; }}
.node text {{ fill: #c0caf5; font-size: 14px; font-weight: 500; }}
.edgePath path {{ stroke: #3b4261; stroke-width: 2px; fill: none; }}
.edgePath marker {{ fill: #3b4261; }}
.edgeLabel text {{ fill: #9aa5ce; font-size: 11px; }}
.edgeLabel rect {{ fill: #1a1b26; opacity: 0.9; }}
.legend {{ position: fixed; top: 20px; right: 20px; background: #1e2030; border: 1px solid #3b4261; border-radius: 8px; padding: 12px 16px; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 0.8rem; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; border: 2px solid; }}
.legend-dot.subprocess {{ border-color: #7dcfff; background: #1e2030; }}
.legend-dot.agent {{ border-color: #bb9af7; background: #1e2030; }}
.legend-dot.gate {{ border-color: #e0af68; background: #1e2030; }}
</style>
</head>
<body>
<h1>Workflow: {workflow_name}</h1>
<div class="meta">Run: {run_id}</div>
<div class="legend">
  <div class="legend-item"><div class="legend-dot subprocess"></div> Subprocess</div>
  <div class="legend-item"><div class="legend-dot agent"></div> Agent</div>
  <div class="legend-item"><div class="legend-dot gate"></div> Gate</div>
</div>
<div id="graph-container"><svg id="svg-canvas"><g/></svg></div>

<script>
// Minimal dagre layout implementation (no external deps)
var graphData = {graph_json};

(function() {{
  var svg = document.getElementById('svg-canvas');
  var g = svg.querySelector('g');
  var nodes = graphData.nodes;
  var edges = graphData.edges;

  var nodeWidth = 180, nodeHeight = 50, padX = 60, padY = 80;
  var labelHeight = 20;

  // Layout: vertical list (linear DAG)
  var totalHeight = nodes.length * (nodeHeight + padY) + padY;
  var totalWidth = nodeWidth + padX * 2 + 200;
  svg.setAttribute('width', totalWidth);
  svg.setAttribute('height', totalHeight);
  svg.setAttribute('viewBox', '0 0 ' + totalWidth + ' ' + totalHeight);

  var centerX = totalWidth / 2;

  // Draw nodes
  nodes.forEach(function(node, i) {{
    var y = padY + i * (nodeHeight + padY);
    var x = centerX - nodeWidth / 2;
    node._x = centerX;
    node._y = y + nodeHeight / 2;

    var group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'node ' + node.category);
    group.setAttribute('transform', 'translate(' + x + ',' + y + ')');

    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', nodeWidth);
    rect.setAttribute('height', nodeHeight);
    group.appendChild(rect);

    var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', nodeWidth / 2);
    text.setAttribute('y', nodeHeight / 2 + 5);
    text.setAttribute('text-anchor', 'middle');
    text.textContent = node.label;
    group.appendChild(text);

    g.appendChild(group);
  }});

  // Draw edges with labels
  edges.forEach(function(edge, i) {{
    var fromNode = nodes.find(function(n) {{ return n.id === edge.from; }});
    var toNode = nodes.find(function(n) {{ return n.id === edge.to; }});
    if (!fromNode || !toNode) return;

    var x1 = fromNode._x, y1 = fromNode._y + nodeHeight / 2;
    var x2 = toNode._x, y2 = toNode._y - nodeHeight / 2;

    // Edge path
    var pathGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    pathGroup.setAttribute('class', 'edgePath');

    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    var midY = (y1 + y2) / 2;
    path.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + x1 + ',' + midY + ' ' + x2 + ',' + midY + ' ' + x2 + ',' + y2);
    pathGroup.appendChild(path);

    // Arrowhead
    var arrowSize = 6;
    var arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    arrow.setAttribute('points',
      (x2 - arrowSize) + ',' + (y2 - arrowSize * 1.5) + ' ' +
      x2 + ',' + y2 + ' ' +
      (x2 + arrowSize) + ',' + (y2 - arrowSize * 1.5));
    arrow.setAttribute('fill', '#3b4261');
    pathGroup.appendChild(arrow);

    g.appendChild(pathGroup);

    // Edge label
    if (edge.label) {{
      var labelGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      labelGroup.setAttribute('class', 'edgeLabel');

      var labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelText.setAttribute('x', centerX + nodeWidth / 2 + 16);
      labelText.setAttribute('y', midY + 4);
      labelText.setAttribute('text-anchor', 'start');
      // Truncate long labels
      var displayLabel = edge.label.length > 50 ? edge.label.substring(0, 47) + '...' : edge.label;
      labelText.textContent = displayLabel;
      labelGroup.appendChild(labelText);

      g.appendChild(labelGroup);
    }}
  }});
}})();
</script>
</body>
</html>
"""


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
