"""agentpipe: deterministic AI pipelines powered by the Claude Agent SDK."""

from agentpipe.display import Display
from agentpipe.models import (
    HAIKU_4_5,
    OPUS_4_6,
    OPUS_4_7,
    SONNET_4_6,
    detect_provider,
    resolve_model,
)
from agentpipe.nodes.base import ClaudeAgentNode, ShellNode, Verbosity
from agentpipe.nodes._old.code_review import code_review_node
from agentpipe.nodes._old.docs_review import docs_review_node
from agentpipe.nodes._old.git_commit import git_commit_node
from agentpipe.nodes._old.git_new_branch import git_new_branch_node
from agentpipe.nodes._old.implement_feature import implement_feature_node
from agentpipe.nodes._old.python_coverage import python_coverage_node
from agentpipe.nodes._old.python_dependency_audit import python_dependency_audit_node
from agentpipe.nodes._old.python_format import python_format_node
from agentpipe.nodes._old.python_implement_feature import python_implement_feature_node
from agentpipe.nodes._old.python_lint import python_lint_node
from agentpipe.nodes._old.python_plan_feature import python_plan_feature_node
from agentpipe.nodes._old.python_test import python_test_node
from agentpipe.nodes._old.resolve_findings import resolve_findings_node
from agentpipe.nodes.resolve_findings import ResolveFindings
from agentpipe.nodes._old.security_audit import security_audit_node
from agentpipe.permissions import PermissionRule, ask_via_stdin
from agentpipe.pipeline import Pipeline
from agentpipe.validation import OutputKeyConflict, validate_node_outputs
from agentpipe.skills import (
    JAVASCRIPT_CLEAN_CODE,
    JAVASCRIPT_SECURITY,
    PYTHON_CLEAN_CODE,
    PYTHON_SECURITY,
    RUST_CLEAN_CODE,
    RUST_SECURITY,
)

__all__ = [
    # Core
    "Pipeline",
    "Display",
    "ClaudeAgentNode",
    "ShellNode",
    "Verbosity",
    # Models
    "HAIKU_4_5",
    "OPUS_4_6",
    "OPUS_4_7",
    "SONNET_4_6",
    "detect_provider",
    "resolve_model",
    # Permissions
    "PermissionRule",
    "ask_via_stdin",
    # Node factories
    "code_review_node",
    "docs_review_node",
    "git_commit_node",
    "git_new_branch_node",
    "implement_feature_node",
    "python_coverage_node",
    "python_dependency_audit_node",
    "python_format_node",
    "python_implement_feature_node",
    "python_lint_node",
    "python_plan_feature_node",
    "python_test_node",
    "ResolveFindings",
    "resolve_findings_node",
    "security_audit_node",
    # Validation
    "OutputKeyConflict",
    "validate_node_outputs",
    # Skills
    "JAVASCRIPT_CLEAN_CODE",
    "JAVASCRIPT_SECURITY",
    "PYTHON_CLEAN_CODE",
    "PYTHON_SECURITY",
    "RUST_CLEAN_CODE",
    "RUST_SECURITY",
]

__version__ = "0.1.0"
