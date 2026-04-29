"""Reusable AgentDefinition instances for Claude Agent SDK multiagent workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.agents.python_code_review import make_code_reviewer as make_code_reviewer
    from codemonkeys.agents.python_docs_review import make_docs_reviewer as make_docs_reviewer
    from codemonkeys.agents.python_security_audit import make_security_auditor as make_security_auditor
    from codemonkeys.agents.review_agent_definition import make_definition_reviewer as make_definition_reviewer

__all__ = [
    "CODE_REVIEWER",
    "DEFINITION_REVIEWER",
    "DEPENDENCY_AUDITOR",
    "DOCS_REVIEWER",
    "FIXER",
    "LINTER",
    "SECURITY_AUDITOR",
    "TEST_RUNNER",
    "TEST_WRITER",
    "TYPE_CHECKER",
    "make_code_reviewer",
    "make_definition_reviewer",
    "make_docs_reviewer",
    "make_security_auditor",
]


def __getattr__(name: str) -> object:
    if name in ("CODE_REVIEWER", "make_code_reviewer"):
        from codemonkeys.agents.python_code_review import CODE_REVIEWER, make_code_reviewer
        return CODE_REVIEWER if name == "CODE_REVIEWER" else make_code_reviewer
    if name in ("DEFINITION_REVIEWER", "make_definition_reviewer"):
        from codemonkeys.agents.review_agent_definition import DEFINITION_REVIEWER, make_definition_reviewer
        return DEFINITION_REVIEWER if name == "DEFINITION_REVIEWER" else make_definition_reviewer
    if name == "DEPENDENCY_AUDITOR":
        from codemonkeys.agents.python_dependency_audit import DEPENDENCY_AUDITOR
        return DEPENDENCY_AUDITOR
    if name in ("DOCS_REVIEWER", "make_docs_reviewer"):
        from codemonkeys.agents.python_docs_review import DOCS_REVIEWER, make_docs_reviewer
        return DOCS_REVIEWER if name == "DOCS_REVIEWER" else make_docs_reviewer
    if name == "FIXER":
        from codemonkeys.agents.python_fixer import FIXER
        return FIXER
    if name == "LINTER":
        from codemonkeys.agents.python_lint import LINTER
        return LINTER
    if name in ("SECURITY_AUDITOR", "make_security_auditor"):
        from codemonkeys.agents.python_security_audit import SECURITY_AUDITOR, make_security_auditor
        return SECURITY_AUDITOR if name == "SECURITY_AUDITOR" else make_security_auditor
    if name == "TEST_RUNNER":
        from codemonkeys.agents.python_test import TEST_RUNNER
        return TEST_RUNNER
    if name == "TEST_WRITER":
        from codemonkeys.agents.python_test_writer import TEST_WRITER
        return TEST_WRITER
    if name == "TYPE_CHECKER":
        from codemonkeys.agents.python_type_check import TYPE_CHECKER
        return TYPE_CHECKER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
