"""Example workflow: review a file, then audit the reviewer's behavior.

Usage:
uv run python -m codemonkeys.review_and_audit
"""

from __future__ import annotations

import asyncio

from codemonkeys.agents.python_file_reviewer import make_python_file_reviewer
from codemonkeys.agents.review_auditor import auditor_from_result
from codemonkeys.core.runner import run_agent
from codemonkeys.core.types import make_log_dir
from codemonkeys.display.logger import FileLogger
from codemonkeys.display.stdout import fan_out, make_stdout_printer

TARGET = "codemonkeys/core/runner.py"


async def main() -> None:
    log_dir = make_log_dir("review_and_audit")
    logger = FileLogger(log_dir / "events.jsonl")
    printer = make_stdout_printer()
    on_event = fan_out(printer, logger.handle)

    reviewer = make_python_file_reviewer([TARGET])
    result = await run_agent(reviewer, "Review the listed files.", on_event=on_event)
    result.save_output(log_dir)

    if result.error:
        logger.close()
        return

    auditor = auditor_from_result(result)
    audit_result = await run_agent(auditor, "Audit this review.", on_event=on_event)
    audit_result.save_output(log_dir)
    logger.close()


if __name__ == "__main__":
    asyncio.run(main())
