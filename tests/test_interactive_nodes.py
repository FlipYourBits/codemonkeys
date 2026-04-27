"""Tests for interactive node factory functions (code_review, security_audit,
git_commit, git_new_branch, python_plan_feature, python_implement_feature).

These test construction, factory output attributes, mode switching, and the
feedback-loop wiring with mocked inner ClaudeAgentNode calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from langclaude.nodes.base import ClaudeAgentNode
from langclaude.nodes.code_review import code_review_node
from langclaude.nodes.docs_review import docs_review_node
from langclaude.nodes.git_commit import git_commit_node
from langclaude.nodes.git_new_branch import git_new_branch_node
from langclaude.nodes.python_implement_feature import python_implement_feature_node
from langclaude.nodes.python_plan_feature import python_plan_feature_node
from langclaude.nodes.security_audit import security_audit_node


# ---------- code_review_node ----------


class TestCodeReviewNode:
    def test_returns_claude_agent_node(self):
        node = code_review_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "code_review"

    def test_custom_name(self):
        node = code_review_node(name="cr2")
        assert node.name == "cr2"

    def test_full_mode(self):
        node = code_review_node(mode="full")
        assert isinstance(node, ClaudeAgentNode)

    def test_diff_mode_prompt_template(self):
        node = code_review_node(mode="diff")
        assert "base_ref" in node.prompt_template

    def test_full_mode_prompt_template(self):
        node = code_review_node(mode="full")
        assert "working_dir" in node.prompt_template

    def test_no_edit_write_in_allow(self):
        node = code_review_node()
        assert "Edit" not in node.allow
        assert "Write" not in node.allow


# ---------- security_audit_node ----------


class TestSecurityAuditNode:
    def test_returns_claude_agent_node(self):
        node = security_audit_node()
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "security_audit"

    def test_full_mode(self):
        node = security_audit_node(mode="full")
        assert isinstance(node, ClaudeAgentNode)

    def test_no_edit_write_in_allow(self):
        node = security_audit_node()
        assert "Edit" not in node.allow
        assert "Write" not in node.allow


# ---------- git_commit_node ----------


class TestGitCommitNode:
    def test_factory_returns_callable_with_attrs(self):
        node = git_commit_node()
        assert callable(node)
        assert node.__name__ == "git_commit"
        assert "git_commit" in node.declared_outputs

    @pytest.mark.asyncio
    async def test_skip_push(self):
        async def skip_push(summary):
            return "skip"

        node = git_commit_node(ask_push=skip_push)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "git_commit_inner": "committed abc123",
                "last_cost_usd": 0.01,
            }
            result = await node({"working_dir": "/tmp"})

        assert result["git_commit"] == "committed abc123"
        assert result["last_cost_usd"] == 0.01

    @pytest.mark.asyncio
    async def test_push_path(self):
        async def do_push(summary):
            return "push"

        node = git_commit_node(ask_push=do_push)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "git_commit_inner": "committed abc",
                "last_cost_usd": 0.01,
            }
            with patch(
                "langclaude.nodes.git_commit._push", return_value="pushed to origin"
            ):
                result = await node({"working_dir": "/tmp"})

        assert "committed abc" in result["git_commit"]
        assert "pushed to origin" in result["git_commit"]

    @pytest.mark.asyncio
    async def test_feedback_loop(self):
        call_count = 0

        async def ask(summary):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "fix the commit message"
            return "skip"

        node = git_commit_node(ask_push=ask)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = [
                {"git_commit_inner": "first", "last_cost_usd": 0.01},
                {"git_commit_inner": "second", "last_cost_usd": 0.02},
            ]
            result = await node({"working_dir": "/tmp"})

        assert result["git_commit"] == "second"
        assert result["last_cost_usd"] == pytest.approx(0.03)


# ---------- git_new_branch_node ----------


class TestGitNewBranchNode:
    def test_factory_returns_callable_with_attrs(self):
        node = git_new_branch_node()
        assert callable(node)
        assert node.__name__ == "git_new_branch"
        assert "git_new_branch" in node.declared_outputs

    @pytest.mark.asyncio
    async def test_auto_mode_clean_tree(self):
        """Auto mode with clean working tree creates branch."""

        async def ask_name(proposed):
            pytest.fail("should not ask in auto mode")

        async def ask_dirty(status):
            pytest.fail("should not ask when clean")

        node = git_new_branch_node(mode="auto", ask_name=ask_name, ask_dirty=ask_dirty)

        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {"git_new_branch_inner": "feat/new-thing"}
            with patch("langclaude.nodes.git_new_branch._is_dirty", return_value=False):
                with patch("langclaude.nodes.git_new_branch._run") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = ""
                    mock_run.return_value.stderr = ""
                    result = await node(
                        {
                            "working_dir": "/tmp/repo",
                            "task_description": "add feature",
                        }
                    )

        assert result["git_new_branch"] == "feat/new-thing"

    @pytest.mark.asyncio
    async def test_interactive_rename(self):
        """Interactive mode: user renames the branch."""

        async def ask_name(proposed):
            return ("rename", "feat/custom-name")

        async def ask_dirty(status):
            return "carry"

        node = git_new_branch_node(
            mode="interactive", ask_name=ask_name, ask_dirty=ask_dirty
        )

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch.object(
                ClaudeAgentNode, "__call__", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = {"git_new_branch_inner": "feat/proposed"}
                with patch(
                    "langclaude.nodes.git_new_branch._is_dirty", return_value=False
                ):
                    with patch("langclaude.nodes.git_new_branch._run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = ""
                        mock_run.return_value.stderr = ""
                        result = await node(
                            {
                                "working_dir": "/tmp",
                                "task_description": "test",
                            }
                        )

        assert result["git_new_branch"] == "feat/custom-name"

    @pytest.mark.asyncio
    async def test_interactive_abort(self):
        """Interactive mode: user aborts."""

        async def ask_name(proposed):
            return ("abort", proposed)

        node = git_new_branch_node(mode="interactive", ask_name=ask_name)

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch.object(
                ClaudeAgentNode, "__call__", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = {"git_new_branch_inner": "feat/x"}
                with pytest.raises(RuntimeError, match="aborted"):
                    await node({"working_dir": "/tmp", "task_description": "t"})

    @pytest.mark.asyncio
    async def test_dirty_tree_stash(self):
        """Interactive mode: user stashes dirty tree."""

        async def ask_name(proposed):
            return ("accept", proposed)

        async def ask_dirty(status):
            return "stash"

        node = git_new_branch_node(
            mode="interactive", ask_name=ask_name, ask_dirty=ask_dirty
        )

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch.object(
                ClaudeAgentNode, "__call__", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = {"git_new_branch_inner": "feat/x"}
                with patch(
                    "langclaude.nodes.git_new_branch._is_dirty", return_value=True
                ):
                    with patch(
                        "langclaude.nodes.git_new_branch._git_status_summary",
                        return_value="M foo.py",
                    ):
                        with patch("langclaude.nodes.git_new_branch._run") as mock_run:
                            mock_run.return_value.returncode = 0
                            mock_run.return_value.stdout = ""
                            mock_run.return_value.stderr = ""
                            result = await node(
                                {
                                    "working_dir": "/tmp",
                                    "task_description": "t",
                                }
                            )

        assert result["git_new_branch"] == "feat/x"

    @pytest.mark.asyncio
    async def test_dirty_tree_commit(self):
        """Interactive mode: user commits dirty tree."""

        async def ask_name(proposed):
            return ("accept", proposed)

        async def ask_dirty(status):
            return "commit:WIP save"

        node = git_new_branch_node(
            mode="interactive", ask_name=ask_name, ask_dirty=ask_dirty
        )

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch.object(
                ClaudeAgentNode, "__call__", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = {"git_new_branch_inner": "feat/x"}
                with patch(
                    "langclaude.nodes.git_new_branch._is_dirty", return_value=True
                ):
                    with patch(
                        "langclaude.nodes.git_new_branch._git_status_summary",
                        return_value="M foo.py",
                    ):
                        with patch("langclaude.nodes.git_new_branch._run") as mock_run:
                            mock_run.return_value.returncode = 0
                            mock_run.return_value.stdout = ""
                            mock_run.return_value.stderr = ""
                            result = await node(
                                {
                                    "working_dir": "/tmp",
                                    "task_description": "t",
                                }
                            )

        assert result["git_new_branch"] == "feat/x"

    @pytest.mark.asyncio
    async def test_dirty_tree_abort(self):
        """Interactive mode: user aborts on dirty tree."""

        async def ask_name(proposed):
            return ("accept", proposed)

        async def ask_dirty(status):
            return "abort"

        node = git_new_branch_node(
            mode="interactive", ask_name=ask_name, ask_dirty=ask_dirty
        )

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch.object(
                ClaudeAgentNode, "__call__", new_callable=AsyncMock
            ) as mock_call:
                mock_call.return_value = {"git_new_branch_inner": "feat/x"}
                with patch(
                    "langclaude.nodes.git_new_branch._is_dirty", return_value=True
                ):
                    with patch(
                        "langclaude.nodes.git_new_branch._git_status_summary",
                        return_value="M foo.py",
                    ):
                        with pytest.raises(RuntimeError, match="aborted"):
                            await node({"working_dir": "/tmp", "task_description": "t"})

    @pytest.mark.asyncio
    async def test_checkout_failure_raises(self):
        """git checkout -b failure raises CalledProcessError."""
        node = git_new_branch_node(mode="auto")

        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {"git_new_branch_inner": "feat/x"}
            with patch("langclaude.nodes.git_new_branch._is_dirty", return_value=False):
                with patch("langclaude.nodes.git_new_branch._run") as mock_run:
                    import subprocess

                    mock_run.return_value.returncode = 128
                    mock_run.return_value.stdout = ""
                    mock_run.return_value.stderr = "branch already exists"
                    with pytest.raises(subprocess.CalledProcessError):
                        await node({"working_dir": "/tmp", "task_description": "t"})


# ---------- python_plan_feature_node ----------


class TestPythonPlanFeatureNode:
    def test_factory_attrs(self):
        node = python_plan_feature_node()
        assert callable(node)
        assert node.__name__ == "python_plan_feature"
        assert "python_plan_feature" in node.declared_outputs

    @pytest.mark.asyncio
    async def test_approve_first_plan(self):
        mock_feedback = AsyncMock(return_value=None)
        node = python_plan_feature_node(ask_feedback=mock_feedback)

        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "python_plan_feature_inner": "Step 1: do X",
                "last_cost_usd": 0.02,
            }
            result = await node(
                {
                    "working_dir": "/tmp",
                    "task_description": "add retry",
                }
            )

        assert result["python_plan_feature"] == "Step 1: do X"

    @pytest.mark.asyncio
    async def test_feedback_revises_plan(self):
        call_count = 0

        async def feedback(plan):
            nonlocal call_count
            call_count += 1
            return "add error handling" if call_count == 1 else None

        node = python_plan_feature_node(ask_feedback=feedback)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = [
                {"python_plan_feature_inner": "v1", "last_cost_usd": 0.01},
                {"python_plan_feature_inner": "v2 with errors", "last_cost_usd": 0.01},
            ]
            result = await node(
                {
                    "working_dir": "/tmp",
                    "task_description": "add feature",
                }
            )

        assert result["python_plan_feature"] == "v2 with errors"


# ---------- python_implement_feature_node ----------


class TestPythonImplementFeatureNode:
    def test_factory_attrs(self):
        node = python_implement_feature_node()
        assert callable(node)
        assert node.__name__ == "python_implement_feature"

    @pytest.mark.asyncio
    async def test_with_plan(self):
        mock_feedback = AsyncMock(return_value=None)
        node = python_implement_feature_node(ask_feedback=mock_feedback)

        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "python_implement_feature_inner": "implemented",
                "last_cost_usd": 0.05,
            }
            result = await node(
                {
                    "working_dir": "/tmp",
                    "task_description": "add retry",
                    "python_plan_feature": "Step 1: create decorator",
                }
            )

        assert result["python_implement_feature"] == "implemented"

    @pytest.mark.asyncio
    async def test_without_plan(self):
        mock_feedback = AsyncMock(return_value=None)
        node = python_implement_feature_node(ask_feedback=mock_feedback)

        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "python_implement_feature_inner": "done",
                "last_cost_usd": 0.03,
            }
            result = await node(
                {
                    "working_dir": "/tmp",
                    "task_description": "add feature",
                }
            )

        assert result["python_implement_feature"] == "done"

    @pytest.mark.asyncio
    async def test_feedback_loop(self):
        call_count = 0

        async def feedback(summary):
            nonlocal call_count
            call_count += 1
            return "fix the types" if call_count == 1 else None

        node = python_implement_feature_node(ask_feedback=feedback)
        with patch.object(
            ClaudeAgentNode, "__call__", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = [
                {"python_implement_feature_inner": "v1", "last_cost_usd": 0.02},
                {"python_implement_feature_inner": "v2 fixed", "last_cost_usd": 0.02},
            ]
            result = await node(
                {
                    "working_dir": "/tmp",
                    "task_description": "task",
                }
            )

        assert result["python_implement_feature"] == "v2 fixed"
        assert result["last_cost_usd"] == pytest.approx(0.04)


# ---------- docs_review_node ----------


class TestDocsReviewNode:
    def test_diff_mode(self):
        node = docs_review_node(mode="diff")
        assert isinstance(node, ClaudeAgentNode)
        assert node.name == "docs_review"

    def test_full_mode(self):
        node = docs_review_node(mode="full")
        assert isinstance(node, ClaudeAgentNode)
        assert "{working_dir}" in node.prompt_template
