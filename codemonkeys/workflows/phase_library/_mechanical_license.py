"""License compliance checker for the mechanical audit."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from codemonkeys.artifacts.schemas.mechanical import LicenseFinding

PYTHON = sys.executable

_PERMISSIVE_LICENSES = frozenset(
    {
        "MIT",
        "MIT License",
        "BSD",
        "BSD License",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "ISC License",
        "Apache-2.0",
        "Apache Software License",
        "Unlicense",
        "The Unlicense",
        "PSF",
        "Python Software Foundation License",
        "Python-2.0",
        "0BSD",
        "CC0-1.0",
        "Public Domain",
    }
)

_COPYLEFT_PATTERNS = re.compile(r"GPL|AGPL|LGPL", re.IGNORECASE)

_RESTRICTIVE_LICENSES = frozenset(
    {
        "MPL-2.0",
        "Mozilla Public License 2.0",
        "MPL 2.0",
        "CC-BY-NC",
        "CC-BY-NC-SA",
        "EUPL",
        "EUPL-1.2",
        "CPAL-1.0",
        "OSL-3.0",
    }
)


def _classify_license(license_str: str) -> tuple[str, str] | None:
    """Classify a license string. Returns (category, severity) or None if permissive."""
    normalized = license_str.strip()

    if not normalized or normalized.upper() == "UNKNOWN":
        return ("unknown_license", "medium")

    if any(normalized.upper().startswith(p.upper()) for p in _PERMISSIVE_LICENSES):
        return None

    if _COPYLEFT_PATTERNS.search(normalized):
        return ("copyleft_risk", "high")

    if any(normalized.upper().startswith(r.upper()) for r in _RESTRICTIVE_LICENSES):
        return ("restrictive_license", "low")

    return ("non_standard_license", "low")


def _run_license_compliance(cwd: Path) -> list[LicenseFinding]:
    """Run pip-licenses and classify each package's license."""
    result = subprocess.run(
        [PYTHON, "-m", "piplicenses", "--format=json", "--with-urls", "--with-system"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if not result.stdout.strip():
        return []

    try:
        raw: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings: list[LicenseFinding] = []
    for item in raw:
        license_str = item.get("License", "")
        classification = _classify_license(license_str)
        if classification is not None:
            category, severity = classification
            findings.append(
                LicenseFinding(
                    package=item.get("Name", ""),
                    version=item.get("Version", ""),
                    license=license_str,
                    category=category,
                    severity=severity,
                )
            )
    return findings
