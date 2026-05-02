"""Reusable AgentDefinition factories for Claude Agent SDK multiagent workflows."""

from __future__ import annotations

from codemonkeys.agents.changelog_reviewer import (
    make_changelog_reviewer as make_changelog_reviewer,
)
from codemonkeys.agents.project_memory import (
    make_project_memory_agent as make_project_memory_agent,
)
from codemonkeys.agents.project_memory import (
    make_project_memory_updater as make_project_memory_updater,
)
from codemonkeys.agents.python_coverage_analyzer import (
    make_python_coverage_analyzer as make_python_coverage_analyzer,
)
from codemonkeys.agents.python_dep_auditor import (
    make_python_dep_auditor as make_python_dep_auditor,
)
from codemonkeys.agents.python_fixer import make_python_fixer as make_python_fixer
from codemonkeys.agents.python_implementer import (
    make_python_implementer as make_python_implementer,
)
from codemonkeys.agents.python_linter import make_python_linter as make_python_linter
from codemonkeys.agents.python_quality_reviewer import (
    make_python_quality_reviewer as make_python_quality_reviewer,
)
from codemonkeys.agents.python_security_auditor import (
    make_python_security_auditor as make_python_security_auditor,
)
from codemonkeys.agents.python_test_runner import (
    make_python_test_runner as make_python_test_runner,
)
from codemonkeys.agents.python_test_writer import (
    make_python_test_writer as make_python_test_writer,
)
from codemonkeys.agents.python_type_checker import (
    make_python_type_checker as make_python_type_checker,
)
from codemonkeys.agents.readme_reviewer import (
    make_readme_reviewer as make_readme_reviewer,
)
from codemonkeys.agents.review_agent_definition import (
    make_definition_reviewer as make_definition_reviewer,
)

__all__ = [
    "make_changelog_reviewer",
    "make_definition_reviewer",
    "make_project_memory_agent",
    "make_project_memory_updater",
    "make_python_coverage_analyzer",
    "make_python_dep_auditor",
    "make_python_fixer",
    "make_python_implementer",
    "make_python_linter",
    "make_python_quality_reviewer",
    "make_python_security_auditor",
    "make_python_test_runner",
    "make_python_test_writer",
    "make_python_type_checker",
    "make_readme_reviewer",
]
