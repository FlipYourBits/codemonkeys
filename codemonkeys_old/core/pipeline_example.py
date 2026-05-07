"""Example pipeline: review, triage, fix.

Usage:
    uv run python -m codemonkeys.core.pipeline_example src/app.py src/utils.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
from codemonkeys.artifacts.schemas.results import FixResult
from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.core.pipeline import PipelineContext, chunked

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": FileFindings.model_json_schema(),
}
FIX_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": FixResult.model_json_schema(),
}


async def review_and_fix(ctx: PipelineContext, files: list[str]) -> None:
    # --- Review ---
    with ctx.phase("review"):
        results = await ctx.run_parallel(
            [
                {
                    "agent": make_python_file_reviewer(batch),
                    "prompt": f"Review: {', '.join(batch)}",
                    "output_format": FINDINGS_SCHEMA,
                    "log_name": "python_file_reviewer",
                    "files": batch[0],
                }
                for batch in chunked(files, 2)
            ]
        )

    all_findings = [
        FileFindings.model_validate(r.structured) for r in results if r.structured
    ]
    total = sum(len(f.findings) for f in all_findings)

    # --- Triage ---
    choice = ctx.prompt(
        f"{total} findings. What to fix?",
        options=["all", "high only", "skip"],
    )

    if choice == "skip" or not choice:
        return

    with ctx.phase("triage"):
        fix_requests: list[FixRequest] = []
        for ff in all_findings:
            findings = ff.findings
            if choice == "high only":
                findings = [f for f in findings if f.severity == "high"]
            if findings:
                fix_requests.append(FixRequest(file=ff.file, findings=findings))

    if not fix_requests:
        return

    # --- Fix ---
    with ctx.phase("fix"):
        await ctx.run_parallel(
            [
                {
                    "agent": make_python_code_fixer(
                        req.file, req.model_dump_json(indent=2)
                    ),
                    "prompt": f"Fix findings in {req.file}",
                    "output_format": FIX_SCHEMA,
                    "log_name": "python_code_fixer",
                    "files": req.file,
                }
                for req in fix_requests
            ]
        )


def main() -> None:
    files = sys.argv[1:]
    if not files:
        print("Usage: python -m codemonkeys.core.pipeline_example <files...>")
        sys.exit(1)

    ctx = PipelineContext("review-and-fix", phases=["review", "triage", "fix"])
    ctx.start()
    try:
        asyncio.run(review_and_fix(ctx, files))
    finally:
        ctx.stop()


if __name__ == "__main__":
    main()
