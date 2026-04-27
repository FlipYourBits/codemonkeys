"""Demo graph: exercises the Display with fake nodes and no LLM calls.

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


def build_pipeline(
    *,
    verbosity: Verbosity = Verbosity.normal,
) -> Pipeline:
    return Pipeline(
        working_dir=".",
        task="demo pipeline",
        steps=[
            "custom/analyze",
            ["custom/lint", "custom/test"],
        ],
        custom_nodes={
            "custom/analyze": demo_node(
                name="analyze",
                output={"files": 12, "issues": 3, "coverage": 87.2},
                delay=2.0,
                steps=5,
                cost=0.042,
            ),
            "custom/lint": demo_node(
                name="lint",
                output={"passed": True, "warnings": 1},
                delay=1.5,
                steps=4,
                cost=0.018,
            ),
            "custom/test": demo_node(
                name="test",
                output={"passed": 42, "failed": 0, "skipped": 2},
                delay=2.5,
                steps=6,
                cost=0.035,
            ),
        },
        config={
            "lint": {"requires": ["analyze"]},
            "test": {"requires": ["analyze"]},
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
    for key in ("analyze", "lint", "test"):
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
