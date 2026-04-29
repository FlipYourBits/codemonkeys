"""Demo graph for testing findings display.

Produces fake findings from two mock nodes and feeds them into
ResolveFindings so you can see the Rich table and prompt without
spending real tokens.  Pick "none" at the prompt to skip fixing.

Usage:
    .venv/bin/python -m codemonkeys.graphs.python.demo_findings
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from pydantic import BaseModel, Field

from codemonkeys.nodes.base import Verbosity
from codemonkeys.nodes.resolve_findings import ResolveFindings
from codemonkeys.pipeline import Pipeline


class FakeFinding(BaseModel):
    severity: str
    file: str
    line: int
    category: str
    description: str
    source: str = ""


class FakeOutput(BaseModel):
    findings: list[FakeFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


_REVIEW_OUTPUT = FakeOutput(
    findings=[
        FakeFinding(
            severity="HIGH",
            file="app/api.py",
            line=42,
            category="logic_error",
            description="Off-by-one in pagination offset causes duplicate results.",
        ),
        FakeFinding(
            severity="MEDIUM",
            file="app/api.py",
            line=88,
            category="error_handling",
            description="Bare except swallows KeyboardInterrupt.",
        ),
        FakeFinding(
            severity="LOW",
            file="app/utils.py",
            line=12,
            category="dead_code",
            description="Unused helper function `_legacy_hash`.",
        ),
    ],
    summary={"total": 3, "high": 1, "medium": 1, "low": 1},
)

_SECURITY_OUTPUT = FakeOutput(
    findings=[
        FakeFinding(
            severity="CRITICAL",
            file="app/auth.py",
            line=15,
            category="injection",
            description="SQL query built with f-string from user input.",
        ),
        FakeFinding(
            severity="HIGH",
            file="app/auth.py",
            line=31,
            category="hardcoded_secret",
            description="JWT signing key hardcoded as string literal.",
        ),
    ],
    summary={"total": 2, "critical": 1, "high": 1},
)


def fake_code_review(state: dict[str, Any]) -> dict[str, Any]:
    return {"fake_code_review": _REVIEW_OUTPUT}


def fake_security_audit(state: dict[str, Any]) -> dict[str, Any]:
    return {"fake_security_audit": _SECURITY_OUTPUT}


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo findings display")
    parser.add_argument(
        "--no-interactive", action="store_true", help="Skip interactive prompt"
    )
    args = parser.parse_args()

    review = fake_code_review
    security = fake_security_audit
    resolve = ResolveFindings(
        reads_from=[review, security],
        interactive=not args.no_interactive,
    )

    pipeline = Pipeline(
        working_dir=".",
        task="Demo findings display",
        steps=[
            [review, security],
            resolve,
        ],
        verbosity=Verbosity.status,
    )
    asyncio.run(pipeline.run())
    pipeline.print_results()


if __name__ == "__main__":
    main()
