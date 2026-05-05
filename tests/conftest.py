"""Pytest configuration — session-wide SDK guard.

Prevents any test from accidentally invoking the real Claude Agent SDK and
spending tokens. Any test that reaches `claude_agent_sdk.query` without an
explicit mock will fail fast with a clear error.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_real_sdk_calls(monkeypatch):
    """Raise if any test triggers a real claude_agent_sdk.query call."""

    async def _forbidden(*args, **kwargs):
        raise RuntimeError(
            "claude_agent_sdk.query was called in a test — patch it with "
            "unittest.mock.AsyncMock or pytest-mock before calling ClaudeAgentNode."
        )
        yield  # noqa: unreachable — makes this an async generator

    monkeypatch.setattr("claude_agent_sdk.query", _forbidden)
