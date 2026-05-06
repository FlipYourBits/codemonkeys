"""Reusable phase functions for review workflows."""

from __future__ import annotations

from codemonkeys.workflows.phase_library.action import fix, report, triage, verify
from codemonkeys.workflows.phase_library.discovery import (
    discover_all_files,
    discover_diff,
    discover_files,
    discover_from_spec,
)
from codemonkeys.workflows.phase_library.mechanical import mechanical_audit
from codemonkeys.workflows.phase_library.refactor import (
    final_verify,
    refactor_step,
    update_readme,
)
from codemonkeys.workflows.phase_library.review import (
    architecture_review,
    doc_review,
    file_review,
    spec_compliance_review,
)
from codemonkeys.workflows.phase_library.stabilize import (
    build_check,
    coverage_measurement,
    dependency_health,
)
from codemonkeys.workflows.phase_library.structural import (
    characterization_tests,
    structural_analysis,
)

__all__ = [
    "architecture_review",
    "build_check",
    "characterization_tests",
    "coverage_measurement",
    "dependency_health",
    "discover_all_files",
    "discover_diff",
    "discover_files",
    "discover_from_spec",
    "doc_review",
    "file_review",
    "final_verify",
    "fix",
    "mechanical_audit",
    "refactor_step",
    "report",
    "spec_compliance_review",
    "structural_analysis",
    "triage",
    "update_readme",
    "verify",
]
