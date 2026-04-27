"""Demo graph: exercises the Display with fake nodes and no LLM calls.

Pipeline shape:

    plan → implement → [lint, test, security] → code_review → commit

Run with:

    python -m langclaude.graphs.demo
    python -m langclaude.graphs.demo --verbosity verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json

from langclaude.display import Display
from langclaude.nodes.base import Verbosity
from langclaude.nodes.demo import demo_node
from langclaude.pipeline import Pipeline

_NODES = {
    "custom/plan": demo_node(
        name="plan",
        output={"steps": ["add retry decorator", "update tests", "update docs"]},
        delay=3.0,
        steps=8,
        cost=0.065,
    ),
    "custom/implement": demo_node(
        name="implement",
        output={"files_changed": 4, "lines_added": 87, "lines_removed": 12},
        delay=4.0,
        steps=10,
        cost=0.120,
    ),
    "custom/lint": demo_node(
        name="lint",
        output={"passed": True, "warnings": 1, "errors": 0},
        delay=1.0,
        steps=3,
        cost=0.008,
    ),
    "custom/test": demo_node(
        name="test",
        output={"passed": 42, "failed": 0, "skipped": 2},
        delay=2.5,
        steps=6,
        cost=0.035,
    ),
    "custom/security": demo_node(
        name="security",
        output={"vulnerabilities": 0, "advisories": 1},
        delay=2.0,
        steps=5,
        cost=0.028,
    ),
    "custom/code_review": demo_node(
        name="code_review",
        output={"approved": True, "comments": 2, "suggestions": 1},
        delay=3.5,
        steps=8,
        cost=0.095,
    ),
    "custom/commit": demo_node(
        name="commit",
        output={"hash": "a1b2c3d", "message": "feat: add retry decorator"},
        delay=1.5,
        steps=4,
        cost=0.012,
    ),
}

_OUTPUT_KEYS = [n.rsplit("/", 1)[-1] for n in _NODES]


def build_pipeline(
    *,
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    return Pipeline(
        working_dir=".",
        task="demo pipeline",
        steps=[
            "custom/plan",
            "custom/implement",
            ["custom/lint", "custom/test", "custom/security"],
            "custom/code_review",
            "custom/commit",
        ],
        custom_nodes=_NODES,
        config={
            "code_review": {"requires": ["implement", "lint", "test", "security"]},
        },
        verbosity=verbosity,
    )


async def main(verbosity: Verbosity = Verbosity.normal) -> None:
    pipeline = build_pipeline(verbosity=verbosity)
    final = await pipeline.run()

    if pipeline._display is not None:
        pipeline._display.print_results(final.get("node_costs", {}))
    else:
        Display(steps=[], title="Demo Results", live=False).print_results(
            final.get("node_costs", {})
        )

    print()
    print("Final node outputs:")
    for key in _OUTPUT_KEYS:
        raw = final.get(key, "{}")
        print(f"  {key}: {json.dumps(json.loads(raw), indent=2)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the demo pipeline.")
    parser.add_argument(
        "--verbosity",
        choices=[v.value for v in Verbosity],
        default=Verbosity.normal.value,
        help="Output verbosity (default: normal)",
    )
    args = parser.parse_args()
    asyncio.run(main(verbosity=Verbosity(args.verbosity)))
