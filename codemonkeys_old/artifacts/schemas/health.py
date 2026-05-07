"""Schemas for build check and dependency health results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildCheckResult(BaseModel):
    loadable: list[str] = Field(description="Modules that imported successfully")
    broken: list[str] = Field(description="Modules that failed to import")
    errors: dict[str, str] = Field(
        description="Module name -> error message for broken modules"
    )


class OutdatedPackage(BaseModel):
    name: str = Field(description="Package name")
    current: str = Field(description="Currently installed version")
    latest: str = Field(description="Latest available version")


class DependencyHealthResult(BaseModel):
    unused: list[str] = Field(description="Installed packages never imported in source")
    missing_lockfile: bool = Field(
        description="Whether uv.lock / poetry.lock / pinned requirements.txt is missing"
    )
    outdated: list[OutdatedPackage] = Field(
        description="Packages with newer versions available"
    )
