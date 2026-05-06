"""Schemas for structural analysis — import graph, cycles, complexity, naming."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileMetrics(BaseModel):
    lines: int = Field(description="Total lines in file")
    function_count: int = Field(description="Number of top-level functions")
    class_count: int = Field(description="Number of top-level classes")
    max_function_length: int = Field(description="Length of longest function in lines")


class LayerViolation(BaseModel):
    source_file: str = Field(description="File that contains the violating import")
    target_file: str = Field(
        description="File being imported in violation of layer rules"
    )
    rule: str = Field(description="The layer rule being violated")


class NamingIssue(BaseModel):
    file: str = Field(description="File containing the naming inconsistency")
    name: str = Field(description="The inconsistent identifier")
    expected_convention: str = Field(
        description="Convention used by the majority of the codebase"
    )
    suggestion: str = Field(description="Suggested replacement name")


class HotFile(BaseModel):
    file: str = Field(description="File path")
    churn: int = Field(description="Number of commits touching this file")
    importers: int = Field(description="Number of other files that import this module")
    risk_score: int = Field(
        description="churn * importers — higher means more impactful to refactor"
    )


class StructuralReport(BaseModel):
    import_graph: dict[str, list[str]] = Field(
        description="Module -> list of modules it imports"
    )
    circular_deps: list[list[str]] = Field(
        description="Each cycle as an ordered list of files"
    )
    file_metrics: dict[str, FileMetrics] = Field(
        description="Per-file complexity stats"
    )
    layer_violations: list[LayerViolation] = Field(
        description="Import-based layer rule violations"
    )
    naming_issues: list[NamingIssue] = Field(
        description="Mixed naming convention issues"
    )
    test_source_map: dict[str, list[str]] = Field(
        description="test_file -> source_files it covers"
    )
    hot_files: list[HotFile] = Field(
        description="Files ordered by risk score (churn * fanout)"
    )
