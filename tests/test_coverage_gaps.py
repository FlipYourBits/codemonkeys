"""Tests targeting uncovered lines in changed-since-main files.

Covers: ask_*_via_stdin functions, git helpers, node constructors,
graph builders, and permissions.ask_via_stdin.
"""

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# permissions.ask_via_stdin  (lines 137-140)
# ---------------------------------------------------------------------------
from agentpipe.permissions import ask_via_stdin


class TestAskViaStdin:
    @pytest.mark.asyncio
    async def test_non_tty_returns_false(self):
        with patch("agentpipe.permissions.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            result = await ask_via_stdin("Bash", {"command": "ls"})
            assert result is False

    @pytest.mark.asyncio
    async def test_tty_yes(self):
        with (
            patch("agentpipe.permissions.sys") as mock_sys,
            patch(
                "agentpipe.permissions.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="y",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await ask_via_stdin("Bash", {"command": "ls"})
            assert result is True

    @pytest.mark.asyncio
    async def test_tty_no(self):
        with (
            patch("agentpipe.permissions.sys") as mock_sys,
            patch(
                "agentpipe.permissions.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="n",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await ask_via_stdin("Bash", {"command": "ls"})
            assert result is False

    @pytest.mark.asyncio
    async def test_tty_truncates_input_keys(self):
        """Covers the summary line that joins first 3 items."""
        with (
            patch("agentpipe.permissions.sys") as mock_sys,
            patch(
                "agentpipe.permissions.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="yes",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await ask_via_stdin("Bash", {"a": 1, "b": 2, "c": 3, "d": 4})
            assert result is True


# ---------------------------------------------------------------------------
# nodes/python_plan_feature.ask_plan_feedback_via_stdin  (lines 50-62)
# ---------------------------------------------------------------------------
from agentpipe.nodes.python_plan_feature import ask_plan_feedback_via_stdin


class TestAskPlanFeedback:
    @pytest.mark.asyncio
    async def test_non_tty_returns_none(self):
        with patch("agentpipe.nodes.python_plan_feature.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            assert await ask_plan_feedback_via_stdin("plan text") is None

    @pytest.mark.asyncio
    async def test_tty_approve_empty(self):
        with (
            patch("agentpipe.nodes.python_plan_feature.sys") as mock_sys,
            patch(
                "agentpipe.nodes.python_plan_feature.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_plan_feedback_via_stdin("plan text") is None

    @pytest.mark.asyncio
    async def test_tty_feedback(self):
        with (
            patch("agentpipe.nodes.python_plan_feature.sys") as mock_sys,
            patch(
                "agentpipe.nodes.python_plan_feature.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="add error handling",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert (
                await ask_plan_feedback_via_stdin("plan text") == "add error handling"
            )


# ---------------------------------------------------------------------------
# nodes/python_implement_feature.ask_impl_feedback_via_stdin  (lines 51-63)
# ---------------------------------------------------------------------------
from agentpipe.nodes.python_implement_feature import ask_impl_feedback_via_stdin


class TestAskImplFeedback:
    @pytest.mark.asyncio
    async def test_non_tty_returns_none(self):
        with patch("agentpipe.nodes.python_implement_feature.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            assert await ask_impl_feedback_via_stdin("summary") is None

    @pytest.mark.asyncio
    async def test_tty_approve(self):
        with (
            patch("agentpipe.nodes.python_implement_feature.sys") as mock_sys,
            patch(
                "agentpipe.nodes.python_implement_feature.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="y",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_impl_feedback_via_stdin("summary") is None

    @pytest.mark.asyncio
    async def test_tty_feedback(self):
        with (
            patch("agentpipe.nodes.python_implement_feature.sys") as mock_sys,
            patch(
                "agentpipe.nodes.python_implement_feature.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="rename the var",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_impl_feedback_via_stdin("summary") == "rename the var"


# ---------------------------------------------------------------------------
# nodes/git_commit: ask_push_via_stdin (lines 53-67) and _push (lines 71-80)
# ---------------------------------------------------------------------------
from agentpipe.nodes.git_commit import _push, ask_push_via_stdin


class TestAskPushViaStdin:
    @pytest.mark.asyncio
    async def test_non_tty_returns_push(self):
        with patch("agentpipe.nodes.git_commit.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            assert await ask_push_via_stdin("summary") == "push"

    @pytest.mark.asyncio
    async def test_tty_push(self):
        with (
            patch("agentpipe.nodes.git_commit.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_commit.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="p",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_push_via_stdin("summary") == "push"

    @pytest.mark.asyncio
    async def test_tty_skip(self):
        with (
            patch("agentpipe.nodes.git_commit.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_commit.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="s",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_push_via_stdin("summary") == "skip"

    @pytest.mark.asyncio
    async def test_tty_feedback(self):
        with (
            patch("agentpipe.nodes.git_commit.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_commit.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="amend the message",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr = MagicMock()
            assert await ask_push_via_stdin("summary") == "amend the message"


class TestPush:
    def test_push_success(self):
        with patch("agentpipe.nodes.git_commit.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stderr="To origin\n  main -> main", stdout=""
            )
            result = _push("/tmp")
            assert "origin" in result

    def test_push_failure(self):
        with patch("agentpipe.nodes.git_commit.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="fatal: no upstream", stdout=""
            )
            result = _push("/tmp")
            assert "push failed" in result

    def test_push_success_stderr_empty_falls_to_stdout(self):
        with patch("agentpipe.nodes.git_commit.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stderr="", stdout="Everything up-to-date"
            )
            result = _push("/tmp")
            assert result == "Everything up-to-date"


# ---------------------------------------------------------------------------
# nodes/git_new_branch: helper functions (lines 86, 90-91, 95-96)
# and ask_* functions (lines 104-116, 124-140)
# ---------------------------------------------------------------------------
from agentpipe.nodes.git_new_branch import (
    _is_dirty,
    _git_status_summary,
    _run,
    ask_branch_name_via_stdin,
    ask_dirty_tree_via_stdin,
)


class TestGitNewBranchHelpers:
    def test_run_returns_completed_process(self):
        result = _run(["echo", "hi"], ".")
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.stdout.strip() == "hi"

    def test_is_dirty_clean(self):
        with patch("agentpipe.nodes.git_new_branch._run") as mock:
            mock.return_value = MagicMock(stdout="")
            assert _is_dirty(".") is False

    def test_is_dirty_dirty(self):
        with patch("agentpipe.nodes.git_new_branch._run") as mock:
            mock.return_value = MagicMock(stdout=" M file.py\n")
            assert _is_dirty(".") is True

    def test_git_status_summary(self):
        with patch("agentpipe.nodes.git_new_branch._run") as mock:
            mock.return_value = MagicMock(stdout=" M file.py\n")
            assert _git_status_summary(".") == "M file.py"


class TestAskBranchNameViaStdin:
    @pytest.mark.asyncio
    async def test_non_tty_auto_accept(self):
        with patch("agentpipe.nodes.git_new_branch.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            action, name = await ask_branch_name_via_stdin("feat/test")
            assert action == "accept"
            assert name == "feat/test"

    @pytest.mark.asyncio
    async def test_tty_accept(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="y",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            action, name = await ask_branch_name_via_stdin("feat/test")
            assert action == "accept"
            assert name == "feat/test"

    @pytest.mark.asyncio
    async def test_tty_rename(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_to_thread,
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_to_thread.side_effect = ["r", "fix/new-name"]
            action, name = await ask_branch_name_via_stdin("feat/old")
            assert action == "rename"
            assert name == "fix/new-name"

    @pytest.mark.asyncio
    async def test_tty_abort(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="a",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            action, name = await ask_branch_name_via_stdin("feat/test")
            assert action == "abort"


class TestAskDirtyTreeViaStdin:
    @pytest.mark.asyncio
    async def test_non_tty_returns_carry(self):
        with patch("agentpipe.nodes.git_new_branch.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            assert await ask_dirty_tree_via_stdin("M file.py") == "carry"

    @pytest.mark.asyncio
    async def test_tty_stash(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="s",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            assert await ask_dirty_tree_via_stdin("M file.py") == "stash"

    @pytest.mark.asyncio
    async def test_tty_commit(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_to_thread,
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_to_thread.side_effect = ["c", "WIP save"]
            result = await ask_dirty_tree_via_stdin("M file.py")
            assert result == "commit:WIP save"

    @pytest.mark.asyncio
    async def test_tty_abort(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="a",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            assert await ask_dirty_tree_via_stdin("M file.py") == "abort"

    @pytest.mark.asyncio
    async def test_tty_carry_default(self):
        with (
            patch("agentpipe.nodes.git_new_branch.sys") as mock_sys,
            patch(
                "agentpipe.nodes.git_new_branch.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="b",
            ),
        ):
            mock_sys.stdin.isatty.return_value = True
            assert await ask_dirty_tree_via_stdin("M file.py") == "carry"


# ---------------------------------------------------------------------------
# nodes/python_coverage: full mode  (line 73)
# ---------------------------------------------------------------------------
from agentpipe.nodes.python_coverage import python_coverage_node


class TestPythonCoverageNode:
    def test_full_mode_prompt(self):
        node = python_coverage_node(mode="full")
        rendered = node._render_prompt({"working_dir": "/repo"})
        assert "FULL mode" in rendered
        assert "/repo" in rendered

    def test_diff_mode_prompt(self):
        node = python_coverage_node(mode="diff")
        rendered = node._render_prompt({"working_dir": "/repo", "base_ref": "main"})
        assert "DIFF mode" in rendered


# ---------------------------------------------------------------------------
# nodes/implement_feature: constructor  (line 55)
# ---------------------------------------------------------------------------
from agentpipe.nodes.implement_feature import implement_feature_node
from agentpipe.nodes.base import ClaudeAgentNode


class TestImplementFeatureNode:
    def test_returns_claude_agent_node(self):
        node = implement_feature_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "implement_feature"

    def test_custom_name(self):
        node = implement_feature_node(name="custom_impl")
        assert node.name == "custom_impl"


# ---------------------------------------------------------------------------
# graphs/python_new_feature.build_pipeline  (partial coverage)
# ---------------------------------------------------------------------------
from agentpipe.graphs.python_new_feature import build_pipeline as build_new_feature


class TestPythonNewFeaturePipeline:
    def test_builds_with_defaults(self):
        p = build_new_feature("/tmp/repo", "add retry")
        assert p.working_dir == "/tmp/repo"
        assert len(p._ordered_names) > 0

    def test_steps_include_branch_and_commit(self):
        p = build_new_feature("/tmp/repo", "add retry")
        assert p.steps[0] == "git_new_branch"
        assert p.steps[-1] == "git_commit"

    def test_config_sets_diff_mode(self):
        p = build_new_feature("/tmp/repo", "task")
        assert p.config.get("code_review") == {"mode": "diff"}
        assert p.config.get("security_audit") == {"mode": "diff"}

    def test_custom_base_ref(self):
        p = build_new_feature("/tmp/repo", "task", base_ref="develop")
        assert p.extra_state.get("base_ref") == "develop"

    def test_verbosity_passthrough(self):
        from agentpipe.nodes.base import Verbosity

        p = build_new_feature("/tmp/repo", "t", verbosity=Verbosity.verbose)
        assert p.verbosity == Verbosity.verbose


# ---------------------------------------------------------------------------
# nodes/git_commit: git_commit_node constructor
# ---------------------------------------------------------------------------
from agentpipe.nodes.git_commit import git_commit_node


class TestGitCommitNodeConstruction:
    def test_returns_async_callable(self):
        node = git_commit_node()
        assert callable(node)
        assert hasattr(node, "declared_outputs")
        assert "git_commit" in node.declared_outputs

    def test_custom_name(self):
        node = git_commit_node(name="my_commit")
        assert node.__name__ == "my_commit"
        assert "my_commit" in node.declared_outputs


# ---------------------------------------------------------------------------
# nodes/git_new_branch: git_new_branch_node constructor
# ---------------------------------------------------------------------------
from agentpipe.nodes.git_new_branch import git_new_branch_node


class TestGitNewBranchNodeConstruction:
    def test_returns_async_callable(self):
        node = git_new_branch_node()
        assert callable(node)
        assert hasattr(node, "declared_outputs")
        assert "git_new_branch" in node.declared_outputs

    def test_custom_name(self):
        node = git_new_branch_node(name="my_branch")
        assert node.__name__ == "my_branch"
        assert "my_branch" in node.declared_outputs


# ---------------------------------------------------------------------------
# nodes/security_audit: security_audit_node constructor
# ---------------------------------------------------------------------------
from agentpipe.nodes.security_audit import security_audit_node


class TestSecurityAuditNodeConstruction:
    def test_returns_claude_agent_node(self):
        node = security_audit_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "security_audit"

    def test_diff_mode(self):
        node = security_audit_node(mode="diff")
        assert isinstance(node, ClaudeAgentNode)

    def test_full_mode(self):
        node = security_audit_node(mode="full")
        assert isinstance(node, ClaudeAgentNode)


# ---------------------------------------------------------------------------
# nodes/python_plan_feature: constructor
# ---------------------------------------------------------------------------
from agentpipe.nodes.python_plan_feature import python_plan_feature_node


class TestPythonPlanFeatureNodeConstruction:
    def test_returns_async_callable(self):
        node = python_plan_feature_node()
        assert callable(node)
        assert hasattr(node, "declared_outputs")
        assert "python_plan_feature" in node.declared_outputs

    def test_custom_name(self):
        node = python_plan_feature_node(name="my_plan")
        assert node.__name__ == "my_plan"


# ---------------------------------------------------------------------------
# nodes/python_implement_feature: constructor
# ---------------------------------------------------------------------------
from agentpipe.nodes.python_implement_feature import python_implement_feature_node


class TestPythonImplFeatureNodeConstruction:
    def test_returns_async_callable(self):
        node = python_implement_feature_node()
        assert callable(node)
        assert hasattr(node, "declared_outputs")
        assert "python_implement_feature" in node.declared_outputs

    def test_custom_name(self):
        node = python_implement_feature_node(name="my_impl")
        assert node.__name__ == "my_impl"
