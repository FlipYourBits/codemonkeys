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
from langclaude.nodes.branch_namer import claude_new_branch_node
from langclaude.nodes.code_review import claude_code_review_node
from langclaude.nodes.dependency_audit import claude_dependency_audit_node
from langclaude.nodes.docs_review import claude_docs_review_node
from langclaude.nodes.feature_implementer import claude_feature_implementer_node
from langclaude.nodes.ruff_node import shell_ruff_fix_node, shell_ruff_fmt_node
from langclaude.nodes.security_audit import claude_security_audit_node
from langclaude.nodes.test_coverage import claude_coverage_node
from langclaude.nodes.test_runner import claude_pytest_node
from langclaude.permissions import (
    PermissionRule,
    ask_via_stdin,
    build_can_use_tool,
)
from langclaude.graphs import chain
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
    "shell_ruff_fix_node",
    "shell_ruff_fmt_node",
    "validate_node_outputs",
]

__version__ = "0.1.0"
