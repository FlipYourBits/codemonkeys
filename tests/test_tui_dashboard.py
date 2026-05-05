from __future__ import annotations

import pytest

from codemonkeys.tui.widgets.agent_card import AgentCard, AgentStatus


class TestAgentCard:
    @pytest.mark.asyncio
    async def test_card_renders_name(self) -> None:
        card = AgentCard(agent_name="python-file-reviewer", task_id="abc123")
        assert card.agent_name == "python-file-reviewer"
        assert card.status == AgentStatus.RUNNING

    def test_status_update(self) -> None:
        card = AgentCard(agent_name="test", task_id="123")
        card.update_progress(
            tokens=1500, tool_calls=3, current_tool="Read(src/main.py)"
        )
        assert card.tokens == 1500
        assert card.tool_calls == 3

    def test_mark_done(self) -> None:
        card = AgentCard(agent_name="test", task_id="123")
        card.mark_done(tokens=5000)
        assert card.status == AgentStatus.DONE
        assert card.tokens == 5000
