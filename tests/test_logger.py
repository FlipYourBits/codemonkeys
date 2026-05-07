import json
import tempfile
import time
from pathlib import Path

from codemonkeys.core.events import AgentStarted, ToolCall
from codemonkeys.display.logger import FileLogger


def test_file_logger_writes_jsonl():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name

    logger = FileLogger(path)
    logger.handle(AgentStarted(agent_name="test", timestamp=1000.0, model="sonnet"))
    logger.handle(
        ToolCall(
            agent_name="test",
            timestamp=1001.0,
            tool_name="Read",
            tool_input={"file_path": "/foo.py"},
        )
    )
    logger.close()

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["agent_name"] == "test"
    assert first["model"] == "sonnet"

    second = json.loads(lines[1])
    assert second["tool_name"] == "Read"


def test_file_logger_as_event_handler():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name

    logger = FileLogger(path)
    event = AgentStarted(agent_name="x", timestamp=time.time(), model="haiku")
    logger.handle(event)
    logger.close()

    lines = Path(path).read_text().strip().split("\n")
    assert len(lines) == 1
