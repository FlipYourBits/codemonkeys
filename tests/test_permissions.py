from __future__ import annotations

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from agentpipe.permissions import PermissionRule, build_can_use_tool


class TestPermissionRule:
    def test_bare_tool_matches_any_input(self):
        rule = PermissionRule.parse("Read")
        assert rule.tool == "Read"
        assert rule.pattern is None
        assert rule.matches("Read", {"file_path": "/anything"})
        assert not rule.matches("Write", {"file_path": "/anything"})

    def test_bash_pattern_matches_command(self):
        rule = PermissionRule.parse("Bash(python*)")
        assert rule.matches("Bash", {"command": "python script.py"})
        assert rule.matches("Bash", {"command": "python3 -m pytest"})
        assert not rule.matches("Bash", {"command": "git push"})

    def test_glob_pattern_for_file_path(self):
        rule = PermissionRule.parse("Edit(*.py)")
        assert rule.matches("Edit", {"file_path": "main.py"})
        assert not rule.matches("Edit", {"file_path": "main.js"})

    def test_malformed_rule_raises(self):
        with pytest.raises(ValueError):
            PermissionRule.parse("Bash(python")
        with pytest.raises(ValueError):
            PermissionRule.parse("")


class TestBuildCanUseTool:
    @pytest.mark.asyncio
    async def test_allow_rule_grants(self):
        cb = build_can_use_tool(allow=["Bash(python*)"], on_unmatched="deny")
        result = await cb("Bash", {"command": "python -V"}, None)
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.asyncio
    async def test_deny_beats_allow(self):
        cb = build_can_use_tool(
            allow=["Bash"],
            deny=["Bash(rm -rf*)"],
            on_unmatched="allow",
        )
        result = await cb("Bash", {"command": "rm -rf /tmp/foo"}, None)
        assert isinstance(result, PermissionResultDeny)

    @pytest.mark.asyncio
    async def test_unmatched_deny_default(self):
        cb = build_can_use_tool(allow=["Read"], on_unmatched="deny")
        result = await cb("Bash", {"command": "ls"}, None)
        assert isinstance(result, PermissionResultDeny)

    @pytest.mark.asyncio
    async def test_unmatched_allow(self):
        cb = build_can_use_tool(allow=[], on_unmatched="allow")
        result = await cb("Bash", {"command": "ls"}, None)
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.asyncio
    async def test_unmatched_callable_yes(self):
        async def yes(_tool, _input):
            return True

        cb = build_can_use_tool(allow=[], on_unmatched=yes)
        result = await cb("Bash", {"command": "ls"}, None)
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.asyncio
    async def test_unmatched_callable_no(self):
        async def no(_tool, _input):
            return False

        cb = build_can_use_tool(allow=[], on_unmatched=no)
        result = await cb("Bash", {"command": "ls"}, None)
        assert isinstance(result, PermissionResultDeny)
