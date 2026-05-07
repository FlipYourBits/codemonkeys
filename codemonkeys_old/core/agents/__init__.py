"""Agent factories for Claude Agent SDK workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.core.agents.architecture_reviewer import (
        make_architecture_reviewer as make_architecture_reviewer,
    )
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
    from codemonkeys.core.agents.python_characterization_tester import (
        make_python_characterization_tester as make_python_characterization_tester,
    )
    from codemonkeys.core.agents.python_structural_refactorer import (
        make_python_structural_refactorer as make_python_structural_refactorer,
    )
    from codemonkeys.core.agents.spec_compliance_reviewer import (
        make_spec_compliance_reviewer as make_spec_compliance_reviewer,
    )

__all__ = [
    "default_registry",
    "make_architecture_reviewer",
    "make_changelog_reviewer",
    "make_python_characterization_tester",
    "make_python_code_fixer",
    "make_python_file_reviewer",
    "make_python_implementer",
    "make_python_structural_refactorer",
    "make_readme_reviewer",
    "make_spec_compliance_reviewer",
]


def __getattr__(name: str) -> object:
    if name == "make_architecture_reviewer":
        from codemonkeys.core.agents.architecture_reviewer import (
            make_architecture_reviewer,
        )

        return make_architecture_reviewer
    if name == "make_changelog_reviewer":
        from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer

        return make_changelog_reviewer
    if name == "make_python_characterization_tester":
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        return make_python_characterization_tester
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
    if name == "make_python_structural_refactorer":
        from codemonkeys.core.agents.python_structural_refactorer import (
            make_python_structural_refactorer,
        )

        return make_python_structural_refactorer
    if name == "make_readme_reviewer":
        from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer

        return make_readme_reviewer
    if name == "make_spec_compliance_reviewer":
        from codemonkeys.core.agents.spec_compliance_reviewer import (
            make_spec_compliance_reviewer,
        )

        return make_spec_compliance_reviewer
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
    from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer
    from codemonkeys.artifacts.schemas.architecture import ArchitectureFindings

    registry.register(
        AgentSpec(
            name="architecture-reviewer",
            role=AgentRole.ANALYZER,
            description="Review codebase for cross-file design issues",
            scope="project",
            produces=ArchitectureFindings,
            consumes=FileFindings,
            make=make_architecture_reviewer,
        )
    )
    from codemonkeys.core.agents.spec_compliance_reviewer import (
        make_spec_compliance_reviewer,
    )
    from codemonkeys.artifacts.schemas.spec_compliance import SpecComplianceFindings

    registry.register(
        AgentSpec(
            name="spec-compliance-reviewer",
            role=AgentRole.ANALYZER,
            description="Compare implementation against spec/plan for completeness and fidelity",
            scope="project",
            produces=SpecComplianceFindings,
            consumes=FeaturePlan,
            make=make_spec_compliance_reviewer,
        )
    )
    from codemonkeys.core.agents.python_characterization_tester import (
        make_python_characterization_tester,
    )
    from codemonkeys.core.agents.python_structural_refactorer import (
        make_python_structural_refactorer,
    )

    from codemonkeys.artifacts.schemas.coverage import CoverageResult
    from codemonkeys.artifacts.schemas.refactor import (
        CharTestResult,
        StructuralRefactorResult,
    )
    from codemonkeys.artifacts.schemas.structural import StructuralReport

    registry.register(
        AgentSpec(
            name="python-characterization-tester",
            role=AgentRole.EXECUTOR,
            description="Write characterization tests for uncovered source files",
            scope="file",
            produces=CharTestResult,
            consumes=CoverageResult,
            make=make_python_characterization_tester,
        )
    )
    registry.register(
        AgentSpec(
            name="python-structural-refactorer",
            role=AgentRole.EXECUTOR,
            description="Execute scoped structural refactoring (cycles, layering, splitting, naming)",
            scope="file",
            produces=StructuralRefactorResult,
            consumes=StructuralReport,
            make=make_python_structural_refactorer,
        )
    )
    return registry
