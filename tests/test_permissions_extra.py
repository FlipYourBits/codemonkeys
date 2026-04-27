"""Extra permission tests: edge cases in PermissionRule.matches and ask_via_stdin."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from langclaude.permissions import PermissionRule, ask_via_stdin


class TestPermissionRuleEdgeCases:
    def test_pattern_unknown_tool_returns_false(self):
        """Pattern rule for tool with no known input field -> no match."""
        rule = PermissionRule.parse("CustomTool(abc*)")
        assert not rule.matches("CustomTool", {"whatever": "abc123"})

    def test_pattern_non_string_value_returns_false(self):
        """Non-string value in the matched field -> no match."""
        rule = PermissionRule.parse("Bash(python*)")
        assert not rule.matches("Bash", {"command": 42})

    def test_pattern_missing_field_returns_false(self):
        """Tool input has no matching field -> no match."""
        rule = PermissionRule.parse("Bash(python*)")
        assert not rule.matches("Bash", {})


class TestAskViaStdin:
    def test_non_tty_returns_false(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = asyncio.get_event_loop().run_until_complete(
                ask_via_stdin("Bash", {"command": "ls"})
            )
            assert result is False
