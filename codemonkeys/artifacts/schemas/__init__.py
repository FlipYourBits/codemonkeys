"""Pydantic models for all artifact types."""

from __future__ import annotations

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding, FixRequest
from codemonkeys.artifacts.schemas.mechanical import (
    CoverageMap,
    CveFinding,
    DeadCodeFinding,
    MechanicalAuditResult,
    PyrightFinding,
    PytestResult,
    RuffFinding,
    SecretsFinding,
)
from codemonkeys.artifacts.schemas.plans import FeaturePlan, PlanStep
from codemonkeys.artifacts.schemas.results import FixResult, VerificationResult
from codemonkeys.artifacts.schemas.spec_compliance import (
    SpecComplianceFinding,
    SpecComplianceFindings,
)

__all__ = [
    "CoverageMap",
    "CveFinding",
    "DeadCodeFinding",
    "FeaturePlan",
    "FileFindings",
    "Finding",
    "FixRequest",
    "FixResult",
    "MechanicalAuditResult",
    "PlanStep",
    "PyrightFinding",
    "PytestResult",
    "RuffFinding",
    "SecretsFinding",
    "SpecComplianceFinding",
    "SpecComplianceFindings",
    "VerificationResult",
]
