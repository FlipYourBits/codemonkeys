"""Example workflow: review a file, then audit the reviewer's behavior.

Usage:
uv run python -m codemonkeys.review_and_audit
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from codemonkeys.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.agents.review_auditor import auditor_from_result
from codemonkeys.core.runner import run_agent
from codemonkeys.display.stdout import make_stdout_printer

TARGET = "codemonkeys/core/runner.py"
LOG_DIR = Path(".codemonkeys") / "logs" / "review_and_audit"


async def main() -> None:
    on_event = make_stdout_printer()

    reviewer = make_python_file_reviewer([TARGET])
    result = await run_agent(reviewer, "Review the listed files.", on_event=on_event)
    result.save_output(LOG_DIR)

    if result.error:
        return

    auditor = auditor_from_result(result)
    audit_result = await run_agent(auditor, "Audit this review.", on_event=on_event)
    audit_result.save_output(LOG_DIR)


if __name__ == "__main__":
    asyncio.run(main())
