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
from agentpipe.nodes.docs_review import DocsReview
from agentpipe.nodes.python_code_review import PythonCodeReview
from agentpipe.nodes.python_dependency_audit import PythonDependencyAudit
from agentpipe.nodes.python_ensure_tools import PythonEnsureTools
from agentpipe.nodes.python_format import PythonFormat
from agentpipe.nodes.python_lint import PythonLint
from agentpipe.nodes.python_security_audit import PythonSecurityAudit
from agentpipe.nodes.python_test import PythonTest
from agentpipe.nodes.python_type_check import PythonTypeCheck
from agentpipe.nodes.resolve_findings import ResolveFindings
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
    # Node classes
    "DocsReview",
    "PythonCodeReview",
    "PythonDependencyAudit",
    "PythonEnsureTools",
    "PythonFormat",
    "PythonLint",
    "PythonSecurityAudit",
    "PythonTest",
    "PythonTypeCheck",
    "ResolveFindings",
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
