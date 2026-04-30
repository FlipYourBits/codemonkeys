"""Reusable AgentDefinition factories for Claude Agent SDK multiagent workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.agents.python_changelog import make_changelog_writer as make_changelog_writer
    from codemonkeys.agents.python_coverage import make_coverage_analyzer as make_coverage_analyzer
    from codemonkeys.agents.python_dep_auditor import make_dep_auditor as make_dep_auditor
    from codemonkeys.agents.python_fixer import make_fixer as make_fixer
    from codemonkeys.agents.python_implementer import make_implementer as make_implementer
    from codemonkeys.agents.python_linter import make_linter as make_linter
    from codemonkeys.agents.python_quality_review import make_quality_reviewer as make_quality_reviewer
    from codemonkeys.agents.python_readme_review import make_readme_reviewer as make_readme_reviewer
    from codemonkeys.agents.python_security_audit import make_security_auditor as make_security_auditor
    from codemonkeys.agents.python_test_runner import make_test_runner as make_test_runner
    from codemonkeys.agents.python_test_writer import make_test_writer as make_test_writer
    from codemonkeys.agents.python_type_checker import make_type_checker as make_type_checker
    from codemonkeys.agents.review_agent_definition import make_definition_reviewer as make_definition_reviewer

__all__ = [
    "make_changelog_writer",
    "make_coverage_analyzer",
    "make_definition_reviewer",
    "make_dep_auditor",
    "make_fixer",
    "make_implementer",
    "make_linter",
    "make_quality_reviewer",
    "make_readme_reviewer",
    "make_security_auditor",
    "make_test_runner",
    "make_test_writer",
    "make_type_checker",
]


def __getattr__(name: str) -> object:
    if name == "make_changelog_writer":
        from codemonkeys.agents.python_changelog import make_changelog_writer
        return make_changelog_writer
    if name == "make_coverage_analyzer":
        from codemonkeys.agents.python_coverage import make_coverage_analyzer
        return make_coverage_analyzer
    if name == "make_definition_reviewer":
        from codemonkeys.agents.review_agent_definition import make_definition_reviewer
        return make_definition_reviewer
    if name == "make_dep_auditor":
        from codemonkeys.agents.python_dep_auditor import make_dep_auditor
        return make_dep_auditor
    if name == "make_fixer":
        from codemonkeys.agents.python_fixer import make_fixer
        return make_fixer
    if name == "make_implementer":
        from codemonkeys.agents.python_implementer import make_implementer
        return make_implementer
    if name == "make_linter":
        from codemonkeys.agents.python_linter import make_linter
        return make_linter
    if name == "make_quality_reviewer":
        from codemonkeys.agents.python_quality_review import make_quality_reviewer
        return make_quality_reviewer
    if name == "make_readme_reviewer":
        from codemonkeys.agents.python_readme_review import make_readme_reviewer
        return make_readme_reviewer
    if name == "make_security_auditor":
        from codemonkeys.agents.python_security_audit import make_security_auditor
        return make_security_auditor
    if name == "make_test_runner":
        from codemonkeys.agents.python_test_runner import make_test_runner
        return make_test_runner
    if name == "make_test_writer":
        from codemonkeys.agents.python_test_writer import make_test_writer
        return make_test_writer
    if name == "make_type_checker":
        from codemonkeys.agents.python_type_checker import make_type_checker
        return make_type_checker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
