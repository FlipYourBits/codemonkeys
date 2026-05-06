"""Tests for workflow graph generation."""

from __future__ import annotations

from pathlib import Path

from codemonkeys.workflows.graph import (
    _build_edge_label,
    _build_graph_data,
    _categorize_phase,
    generate_workflow_graph,
)
from codemonkeys.workflows.phases import Phase, PhaseType, Workflow, WorkflowContext


def _make_workflow() -> Workflow:
    async def noop(ctx: WorkflowContext) -> dict:
        return {}

    return Workflow(
        name="test_workflow",
        phases=[
            Phase(name="discover", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(
                name="mechanical_audit", phase_type=PhaseType.AUTOMATED, execute=noop
            ),
            Phase(name="file_review", phase_type=PhaseType.AUTOMATED, execute=noop),
            Phase(name="triage", phase_type=PhaseType.GATE, execute=noop),
            Phase(name="fix", phase_type=PhaseType.AUTOMATED, execute=noop),
        ],
    )


class TestCategorizePhase:
    def test_subprocess_phases(self) -> None:
        assert _categorize_phase("discover", PhaseType.AUTOMATED) == "subprocess"
        assert (
            _categorize_phase("mechanical_audit", PhaseType.AUTOMATED) == "subprocess"
        )
        assert _categorize_phase("verify", PhaseType.AUTOMATED) == "subprocess"

    def test_agent_phases(self) -> None:
        assert _categorize_phase("file_review", PhaseType.AUTOMATED) == "agent"
        assert _categorize_phase("architecture_review", PhaseType.AUTOMATED) == "agent"

    def test_gate_phases(self) -> None:
        assert _categorize_phase("triage", PhaseType.GATE) == "gate"


class TestBuildEdgeLabel:
    def test_list_value(self) -> None:
        label = _build_edge_label({"files": ["a.py", "b.py", "c.py"]})
        assert "3 files" in label

    def test_none_result(self) -> None:
        assert _build_edge_label(None) == ""

    def test_empty_dict(self) -> None:
        assert _build_edge_label({}) == ""

    def test_mixed_values(self) -> None:
        label = _build_edge_label({"files": ["a.py"], "metadata": "long" * 50})
        assert "1 files" in label
        assert "chars" in label


class TestBuildGraphData:
    def test_produces_nodes_and_edges(self) -> None:
        wf = _make_workflow()
        ctx = WorkflowContext(
            cwd="/tmp",
            run_id="test/run1",
            phase_results={
                "discover": {"files": ["a.py", "b.py"]},
                "mechanical_audit": {"mechanical": None},
                "file_review": {"file_findings": []},
                "triage": {"fix_requests": []},
            },
        )
        data = _build_graph_data(wf, ctx)

        assert data["workflow"] == "test_workflow"
        assert len(data["nodes"]) == 5
        assert len(data["edges"]) == 4

        categories = {n["category"] for n in data["nodes"]}
        assert "subprocess" in categories
        assert "agent" in categories
        assert "gate" in categories

    def test_edge_labels_from_results(self) -> None:
        wf = _make_workflow()
        ctx = WorkflowContext(
            cwd="/tmp",
            run_id="test/run1",
            phase_results={
                "discover": {"files": ["a.py", "b.py", "c.py"]},
            },
        )
        data = _build_graph_data(wf, ctx)
        first_edge = data["edges"][0]
        assert first_edge["from"] == "discover"
        assert "3 files" in first_edge["label"]


class TestGenerateWorkflowGraph:
    def test_generates_html_file(self, tmp_path: Path) -> None:
        wf = _make_workflow()
        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            phase_results={
                "discover": {"files": ["a.py"]},
                "mechanical_audit": {"mechanical": None},
                "file_review": {"file_findings": []},
                "triage": {"fix_requests": []},
                "fix": {"fix_results": []},
            },
        )
        output = generate_workflow_graph(wf, ctx, output_dir=tmp_path)

        assert output.exists()
        assert output.name == "workflow_graph.html"
        content = output.read_text()
        assert "test_workflow" in content
        assert "graphData" in content
        assert "discover" in content

    def test_default_output_dir(self, tmp_path: Path) -> None:
        wf = _make_workflow()
        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            phase_results={},
        )
        output = generate_workflow_graph(wf, ctx)
        assert output == tmp_path / ".codemonkeys" / "test/run1" / "workflow_graph.html"
        assert output.exists()
