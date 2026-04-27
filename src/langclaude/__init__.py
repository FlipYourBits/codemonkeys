"""langclaude: LangGraph nodes powered by the Claude Agent SDK."""

from langclaude.budget import BudgetTracker, default_on_warn
from langclaude.models import (
    DEFAULT,
    HAIKU_4_5,
    OPUS_4_6,
    OPUS_4_7,
    SONNET_4_6,
)
from langclaude.nodes.base import ClaudeAgentNode, ShellNode
from langclaude.nodes.new_branch import claude_new_branch_node
from langclaude.nodes.code_review import claude_code_review_node
from langclaude.nodes.dependency_audit import claude_dependency_audit_node
from langclaude.nodes.docs_review import claude_docs_review_node
from langclaude.nodes.implement_feature import claude_feature_implementer_node
from langclaude.nodes.ruff import shell_ruff_fix_node, shell_ruff_fmt_node
from langclaude.nodes.security_audit import claude_security_audit_node
from langclaude.nodes.coverage import claude_coverage_node
from langclaude.nodes.pytest_node import claude_pytest_node
from langclaude.permissions import (
    PermissionRule,
    ask_via_stdin,
    build_can_use_tool,
)
from langclaude.graphs import chain
from langclaude.pipeline import Pipeline
from langclaude.registry import (
    list_builtins,
    list_registered,
    register,
    resolve,
)
from langclaude.validation import (
    MERGE_OK_KEYS,
    OutputKeyConflict,
    validate_node_outputs,
)

__all__ = [
    "BudgetTracker",
    "ClaudeAgentNode",
    "DEFAULT",
    "HAIKU_4_5",
    "MERGE_OK_KEYS",
    "OPUS_4_6",
    "OPUS_4_7",
    "OutputKeyConflict",
    "PermissionRule",
    "Pipeline",
    "SONNET_4_6",
    "ShellNode",
    "ask_via_stdin",
    "build_can_use_tool",
    "chain",
    "claude_new_branch_node",
    "claude_code_review_node",
    "claude_docs_review_node",
    "claude_feature_implementer_node",
    "claude_security_audit_node",
    "default_on_warn",
    "claude_coverage_node",
    "claude_dependency_audit_node",
    "claude_pytest_node",
    "list_builtins",
    "list_registered",
    "register",
    "resolve",
    "shell_ruff_fix_node",
    "shell_ruff_fmt_node",
    "validate_node_outputs",
]

__version__ = "0.1.0"
