"""codemonkeys: deterministic AI pipelines powered by the Claude Agent SDK."""

from codemonkeys.display import Display
from codemonkeys.models import (
    HAIKU_4_5,
    OPUS_4_6,
    OPUS_4_7,
    SONNET_4_6,
    detect_provider,
    resolve_model,
)
from codemonkeys.nodes.base import ClaudeAgentNode, ShellNode, Verbosity
from codemonkeys.nodes.docs_review import DocsReview
from codemonkeys.nodes.python_code_review import PythonCodeReview
from codemonkeys.nodes.python_dependency_audit import PythonDependencyAudit
from codemonkeys.nodes.python_ensure_tools import PythonEnsureTools
from codemonkeys.nodes.python_format import PythonFormat
from codemonkeys.nodes.python_lint import PythonLint
from codemonkeys.nodes.python_security_audit import PythonSecurityAudit
from codemonkeys.nodes.python_test import PythonTest
from codemonkeys.nodes.python_type_check import PythonTypeCheck
from codemonkeys.nodes.resolve_findings import ResolveFindings
from codemonkeys.permissions import PermissionRule, ask_via_stdin
from codemonkeys.pipeline import Pipeline
from codemonkeys.validation import OutputKeyConflict, validate_node_outputs
from codemonkeys.skills import (
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
