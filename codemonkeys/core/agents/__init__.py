"""Agent factories for Claude Agent SDK workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.core.agents.changelog_reviewer import (
        make_changelog_reviewer as make_changelog_reviewer,
    )
    from codemonkeys.core.agents.python_code_fixer import (
        make_python_code_fixer as make_python_code_fixer,
    )
    from codemonkeys.core.agents.python_file_reviewer import (
        make_python_file_reviewer as make_python_file_reviewer,
    )
    from codemonkeys.core.agents.python_implementer import (
        make_python_implementer as make_python_implementer,
    )
    from codemonkeys.core.agents.readme_reviewer import (
        make_readme_reviewer as make_readme_reviewer,
    )
    from codemonkeys.core.agents.registry import AgentRegistry as AgentRegistry

__all__ = [
    "default_registry",
    "make_changelog_reviewer",
    "make_python_code_fixer",
    "make_python_file_reviewer",
    "make_python_implementer",
    "make_readme_reviewer",
]


def __getattr__(name: str) -> object:
    if name == "make_changelog_reviewer":
        from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer

        return make_changelog_reviewer
    if name == "make_python_code_fixer":
        from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer

        return make_python_code_fixer
    if name == "make_python_file_reviewer":
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        return make_python_file_reviewer
    if name == "make_python_implementer":
        from codemonkeys.core.agents.python_implementer import make_python_implementer

        return make_python_implementer
    if name == "make_readme_reviewer":
        from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer

        return make_readme_reviewer
    if name == "default_registry":
        return default_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def default_registry() -> "AgentRegistry":
    """Build a registry with all built-in agents."""
    from codemonkeys.artifacts.schemas.findings import FileFindings, FixRequest
    from codemonkeys.artifacts.schemas.plans import FeaturePlan
    from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer
    from codemonkeys.core.agents.python_code_fixer import make_python_code_fixer
    from codemonkeys.core.agents.python_file_reviewer import make_python_file_reviewer
    from codemonkeys.core.agents.python_implementer import make_python_implementer
    from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer
    from codemonkeys.core.agents.registry import AgentRegistry, AgentRole, AgentSpec

    registry = AgentRegistry()
    registry.register(
        AgentSpec(
            name="python-file-reviewer",
            role=AgentRole.ANALYZER,
            description="Review a Python file for code quality and security issues",
            scope="file",
            produces=FileFindings,
            consumes=None,
            make=make_python_file_reviewer,
        )
    )
    registry.register(
        AgentSpec(
            name="changelog-reviewer",
            role=AgentRole.ANALYZER,
            description="Check CHANGELOG.md accuracy against git history",
            scope="project",
            produces=FileFindings,
            consumes=None,
            make=make_changelog_reviewer,
        )
    )
    registry.register(
        AgentSpec(
            name="readme-reviewer",
            role=AgentRole.ANALYZER,
            description="Verify README.md claims against the codebase",
            scope="project",
            produces=FileFindings,
            consumes=None,
            make=make_readme_reviewer,
        )
    )
    registry.register(
        AgentSpec(
            name="python-code-fixer",
            role=AgentRole.EXECUTOR,
            description="Fix specific findings in a Python file",
            scope="file",
            produces=None,
            consumes=FixRequest,
            make=make_python_code_fixer,
        )
    )
    registry.register(
        AgentSpec(
            name="python-implementer",
            role=AgentRole.EXECUTOR,
            description="Implement a feature from an approved plan using TDD",
            scope="project",
            produces=None,
            consumes=FeaturePlan,
            make=make_python_implementer,
        )
    )
    return registry
