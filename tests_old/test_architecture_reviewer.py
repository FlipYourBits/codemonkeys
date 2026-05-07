from __future__ import annotations

from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer

SAMPLE_METADATA = """\
### `src/a.py`
  External imports: requests
  fetch_prices() -> list[float]

### `src/b.py`
  External imports: websockets
  class PriceFeed(BaseModel):
    async connect() -> None"""


def _make(**overrides):
    defaults = {
        "files": ["src/a.py", "src/b.py"],
        "file_summaries": [
            {"file": "src/a.py", "summary": "HTTP price fetcher"},
            {"file": "src/b.py", "summary": "WebSocket price feed"},
        ],
        "structural_metadata": SAMPLE_METADATA,
    }
    defaults.update(overrides)
    return make_architecture_reviewer(**defaults)


class TestArchitectureReviewer:
    def test_returns_agent_definition(self) -> None:
        agent = _make()
        assert agent.model == "opus"

    def test_prompt_contains_design_review_checklist(self) -> None:
        agent = _make()
        assert "paradigm_inconsistency" in agent.prompt
        assert "layer_violation" in agent.prompt
        assert "Design Review Checklist" in agent.prompt

    def test_prompt_contains_file_summaries(self) -> None:
        agent = _make()
        assert "src/a.py" in agent.prompt
        assert "HTTP price fetcher" in agent.prompt
        assert "src/b.py" in agent.prompt

    def test_prompt_contains_structural_metadata(self) -> None:
        agent = _make()
        assert "fetch_prices() -> list[float]" in agent.prompt
        assert "class PriceFeed(BaseModel)" in agent.prompt

    def test_has_read_tool_for_spot_checks(self) -> None:
        agent = _make()
        assert "Read" in agent.tools

    def test_no_grep_tool(self) -> None:
        agent = _make()
        assert "Grep" not in agent.tools

    def test_no_memory(self) -> None:
        agent = _make()
        assert agent.memory is None

    def test_permission_mode_is_dont_ask(self) -> None:
        agent = _make()
        assert agent.permissionMode == "dontAsk"
