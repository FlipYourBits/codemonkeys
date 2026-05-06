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


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Workflow: {workflow_name} — {run_id}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1b26; color: #c0caf5; padding: 20px; display: flex; gap: 24px; }}
h1 {{ font-size: 1.2rem; margin-bottom: 16px; color: #7aa2f7; }}
.meta {{ font-size: 0.85rem; color: #565f89; margin-bottom: 24px; }}
#graph-panel {{ flex: 1; min-width: 400px; }}
#detail-panel {{ width: 420px; position: sticky; top: 20px; align-self: flex-start; max-height: calc(100vh - 40px); overflow-y: auto; }}
#detail-panel.hidden {{ display: none; }}
#detail-content {{ background: #1e2030; border: 1px solid #3b4261; border-radius: 8px; padding: 16px; }}
#detail-content h2 {{ font-size: 1rem; color: #7aa2f7; margin-bottom: 12px; }}
#detail-content h3 {{ font-size: 0.85rem; color: #bb9af7; margin: 12px 0 6px; }}
.detail-item {{ margin: 6px 0; padding: 8px; background: #16161e; border-radius: 4px; font-size: 0.8rem; }}
.detail-item .key {{ color: #7dcfff; font-weight: 600; }}
.detail-item .type {{ color: #565f89; margin-left: 8px; }}
.detail-item .summary {{ color: #9aa5ce; display: block; margin-top: 4px; }}
.detail-item .items {{ color: #565f89; margin-top: 4px; font-family: monospace; font-size: 0.75rem; max-height: 120px; overflow-y: auto; }}
.detail-item .items div {{ padding: 1px 0; }}
.detail-item .preview {{ color: #565f89; margin-top: 4px; font-family: monospace; font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; max-height: 80px; overflow-y: auto; }}
.detail-item .fields {{ margin-top: 4px; font-family: monospace; font-size: 0.75rem; color: #565f89; }}
.detail-item .fields div {{ padding: 1px 0; }}
.hint {{ font-size: 0.75rem; color: #565f89; text-align: center; margin-top: 8px; }}
svg {{ display: block; }}
.node {{ cursor: pointer; }}
.node rect {{ stroke-width: 2px; rx: 8; ry: 8; transition: stroke-width 0.15s; }}
.node:hover rect {{ stroke-width: 3px; }}
.node.selected rect {{ stroke-width: 3px; filter: brightness(1.3); }}
.node.subprocess rect {{ fill: #1e2030; stroke: #7dcfff; }}
.node.agent rect {{ fill: #1e2030; stroke: #bb9af7; }}
.node.gate rect {{ fill: #1e2030; stroke: #e0af68; }}
.node text {{ fill: #c0caf5; font-size: 14px; font-weight: 500; pointer-events: none; }}
.edgePath path {{ stroke: #3b4261; stroke-width: 2px; fill: none; }}
.edgeLabel text {{ fill: #9aa5ce; font-size: 11px; }}
.legend {{ position: fixed; top: 20px; right: 20px; background: #1e2030; border: 1px solid #3b4261; border-radius: 8px; padding: 12px 16px; z-index: 10; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 0.8rem; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; border: 2px solid; }}
.legend-dot.subprocess {{ border-color: #7dcfff; background: #1e2030; }}
.legend-dot.agent {{ border-color: #bb9af7; background: #1e2030; }}
.legend-dot.gate {{ border-color: #e0af68; background: #1e2030; }}
</style>
</head>
<body>
<div id="graph-panel">
  <h1>Workflow: {workflow_name}</h1>
  <div class="meta">Run: {run_id}</div>
  <svg id="svg-canvas"><g/></svg>
  <div class="hint">Click a node to inspect its outputs</div>
</div>
<div id="detail-panel" class="hidden">
  <div id="detail-content"></div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-dot subprocess"></div> Subprocess</div>
  <div class="legend-item"><div class="legend-dot agent"></div> Agent</div>
  <div class="legend-item"><div class="legend-dot gate"></div> Gate</div>
</div>

<script>
var graphData = {graph_json};

(function() {{
  var svg = document.getElementById('svg-canvas');
  var g = svg.querySelector('g');
  var nodes = graphData.nodes;
  var edges = graphData.edges;
  var detailPanel = document.getElementById('detail-panel');
  var detailContent = document.getElementById('detail-content');
  var selectedNode = null;

  var nodeWidth = 180, nodeHeight = 50, padX = 60, padY = 80;

  var totalHeight = nodes.length * (nodeHeight + padY) + padY;
  var totalWidth = nodeWidth + padX * 2 + 200;
  svg.setAttribute('width', totalWidth);
  svg.setAttribute('height', totalHeight);
  svg.setAttribute('viewBox', '0 0 ' + totalWidth + ' ' + totalHeight);

  var centerX = totalWidth / 2;

  function showDetail(node) {{
    if (selectedNode) {{
      selectedNode.classList.remove('selected');
    }}

    var outputs = node.output || [];
    var html = '<h2>' + node.label + '</h2>';
    html += '<span style="font-size:0.75rem;color:#565f89">Category: ' + node.category + '</span>';

    if (outputs.length === 0) {{
      html += '<p style="color:#565f89;margin-top:12px;font-size:0.85rem">(no output data)</p>';
    }} else {{
      html += '<h3>Outputs</h3>';
      outputs.forEach(function(item) {{
        html += '<div class="detail-item">';
        html += '<span class="key">' + item.key + '</span>';
        html += '<span class="type">' + item.type + '</span>';
        if (item.summary) {{
          html += '<span class="summary">' + item.summary + '</span>';
        }}
        if (item.items) {{
          html += '<div class="items">';
          item.items.forEach(function(it) {{
            html += '<div>' + escHtml(it) + '</div>';
          }});
          if (item.truncated) html += '<div>...</div>';
          html += '</div>';
        }}
        if (item.preview) {{
          html += '<div class="preview">' + escHtml(item.preview) + '</div>';
        }}
        if (item.fields) {{
          html += '<div class="fields">';
          Object.keys(item.fields).forEach(function(k) {{
            html += '<div><span style="color:#7dcfff">' + k + '</span>: ' + escHtml(item.fields[k]) + '</div>';
          }});
          html += '</div>';
        }}
        html += '</div>';
      }});
    }}

    detailContent.innerHTML = html;
    detailPanel.classList.remove('hidden');
  }}

  function escHtml(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}

  // Draw nodes
  nodes.forEach(function(node, i) {{
    var y = padY + i * (nodeHeight + padY);
    var x = centerX - nodeWidth / 2;
    node._x = centerX;
    node._y = y + nodeHeight / 2;

    var group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'node ' + node.category);
    group.setAttribute('transform', 'translate(' + x + ',' + y + ')');
    group.setAttribute('data-id', node.id);

    group.addEventListener('click', function() {{
      if (selectedNode) selectedNode.classList.remove('selected');
      group.classList.add('selected');
      selectedNode = group;
      showDetail(node);
    }});

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

    var pathGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    pathGroup.setAttribute('class', 'edgePath');

    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    var midY = (y1 + y2) / 2;
    path.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + x1 + ',' + midY + ' ' + x2 + ',' + midY + ' ' + x2 + ',' + y2);
    pathGroup.appendChild(path);

    var arrowSize = 6;
    var arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    arrow.setAttribute('points',
      (x2 - arrowSize) + ',' + (y2 - arrowSize * 1.5) + ' ' +
      x2 + ',' + y2 + ' ' +
      (x2 + arrowSize) + ',' + (y2 - arrowSize * 1.5));
    arrow.setAttribute('fill', '#3b4261');
    pathGroup.appendChild(arrow);

    g.appendChild(pathGroup);

    if (edge.label) {{
      var labelGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      labelGroup.setAttribute('class', 'edgeLabel');

      var labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelText.setAttribute('x', centerX + nodeWidth / 2 + 16);
      labelText.setAttribute('y', midY + 4);
      labelText.setAttribute('text-anchor', 'start');
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
