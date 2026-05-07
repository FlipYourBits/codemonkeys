"""File logger — writes events as JSONL."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import IO

from codemonkeys.core.events import Event


class FileLogger:
    """Writes events as JSON lines to a file.

    Usage:
        logger = FileLogger("run.jsonl")
        result = await run_agent(agent, prompt, on_event=logger.handle)
        logger.close()
    """

    def __init__(self, path: str | Path) -> None:
        self._file: IO[str] = open(path, "a")

    def handle(self, event: Event) -> None:
        data = asdict(event)
        data["_type"] = type(event).__name__
        self._file.write(json.dumps(data, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
