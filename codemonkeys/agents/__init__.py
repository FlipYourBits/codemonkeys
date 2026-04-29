"""Reusable AgentDefinition instances for Claude Agent SDK multiagent workflows."""

from codemonkeys.agents.prompt_review import PROMPT_REVIEWER
from codemonkeys.agents.python_code_review import CODE_REVIEWER
from codemonkeys.agents.python_dependency_audit import DEPENDENCY_AUDITOR
from codemonkeys.agents.python_docs_review import DOCS_REVIEWER
from codemonkeys.agents.python_fixer import FIXER
from codemonkeys.agents.python_lint import LINTER
from codemonkeys.agents.python_security_audit import SECURITY_AUDITOR
from codemonkeys.agents.python_test import TEST_RUNNER
from codemonkeys.agents.python_type_check import TYPE_CHECKER

__all__ = [
    "CODE_REVIEWER",
    "DEPENDENCY_AUDITOR",
    "DOCS_REVIEWER",
    "FIXER",
    "LINTER",
    "PROMPT_REVIEWER",
    "SECURITY_AUDITOR",
    "TEST_RUNNER",
    "TYPE_CHECKER",
]
