"""Dependency-audit node: runs SCA tools against lockfiles and emits
findings in the standard schema. Purely deterministic — no LLM call.

Detects ecosystem from manifest files and runs the matching scanner
when it's installed: pip-audit, npm/yarn audit, govulncheck, cargo audit,
bundler-audit. Missing scanners are skipped (recorded in
`dep_scanners_skipped`).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


_SEVERITY_MAP = {
    "critical": "HIGH",
    "high": "HIGH",
    "moderate": "MEDIUM",
    "medium": "MEDIUM",
    "low": "LOW",
    "info": "LOW",
}


def _norm_severity(raw: Any) -> str:
    return _SEVERITY_MAP.get(str(raw or "").lower(), "MEDIUM")


def _run(argv: list[str], cwd: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=300, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def _pip_audit(cwd: str) -> list[dict[str, Any]]:
    if not shutil.which("pip-audit"):
        return []
    _, stdout, _ = _run(["pip-audit", "--format", "json"], cwd)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    findings: list[dict[str, Any]] = []
    for entry in data.get("dependencies", data) or []:
        for vuln in entry.get("vulns", []) or []:
            findings.append(
                {
                    "file": "pyproject.toml",
                    "line": 0,
                    "severity": _norm_severity(vuln.get("severity")),
                    "category": "vulnerable_dependency",
                    "source": "pip-audit",
                    "description": (
                        f"{entry.get('name')}=={entry.get('version')} — "
                        f"{vuln.get('id')}: {vuln.get('description', '').splitlines()[0] if vuln.get('description') else ''}"
                    ).strip(),
                    "recommendation": (
                        f"Upgrade {entry.get('name')} to a fixed version: "
                        f"{', '.join(vuln.get('fix_versions') or []) or 'see advisory'}"
                    ),
                    "confidence": 1.0,
                    "vuln_id": vuln.get("id"),
                    "package": entry.get("name"),
                    "version": entry.get("version"),
                }
            )
    return findings


def _npm_audit(cwd: str) -> list[dict[str, Any]]:
    if not shutil.which("npm"):
        return []
    _, stdout, _ = _run(["npm", "audit", "--json"], cwd)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    findings: list[dict[str, Any]] = []
    for name, advisory in (data.get("vulnerabilities") or {}).items():
        via = advisory.get("via") or []
        details = next((v for v in via if isinstance(v, dict)), {})
        findings.append(
            {
                "file": "package.json",
                "line": 0,
                "severity": _norm_severity(advisory.get("severity")),
                "category": "vulnerable_dependency",
                "source": "npm-audit",
                "description": (
                    f"{name} — {details.get('title') or details.get('source') or 'advisory'}"
                ),
                "recommendation": (
                    f"Run `npm audit fix` or upgrade {name} to "
                    f"{advisory.get('fixAvailable') or 'a patched version'}"
                ),
                "confidence": 1.0,
                "package": name,
            }
        )
    return findings


def _govulncheck(cwd: str) -> list[dict[str, Any]]:
    if not shutil.which("govulncheck"):
        return []
    _, stdout, _ = _run(["govulncheck", "-json", "./..."], cwd)
    findings: list[dict[str, Any]] = []
    for raw in stdout.splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        finding = entry.get("finding") or entry.get("osv")
        if not isinstance(finding, dict):
            continue
        osv = finding.get("osv") or finding
        findings.append(
            {
                "file": "go.mod",
                "line": 0,
                "severity": "HIGH",
                "category": "vulnerable_dependency",
                "source": "govulncheck",
                "description": (
                    f"{osv.get('id', '?')}: {(osv.get('summary') or osv.get('details') or '').splitlines()[0]}"
                ),
                "recommendation": "Upgrade the affected module — see advisory.",
                "confidence": 1.0,
                "vuln_id": osv.get("id"),
            }
        )
    return findings


def _cargo_audit(cwd: str) -> list[dict[str, Any]]:
    if not shutil.which("cargo"):
        return []
    _, stdout, _ = _run(["cargo", "audit", "--json"], cwd)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    findings: list[dict[str, Any]] = []
    for v in (data.get("vulnerabilities") or {}).get("list") or []:
        adv = v.get("advisory") or {}
        pkg = v.get("package") or {}
        findings.append(
            {
                "file": "Cargo.lock",
                "line": 0,
                "severity": _norm_severity(adv.get("severity")),
                "category": "vulnerable_dependency",
                "source": "cargo-audit",
                "description": f"{pkg.get('name')} {pkg.get('version')} — {adv.get('id')}: {adv.get('title')}",
                "recommendation": f"Upgrade {pkg.get('name')} — see {adv.get('url') or 'advisory'}",
                "confidence": 1.0,
                "vuln_id": adv.get("id"),
                "package": pkg.get("name"),
                "version": pkg.get("version"),
            }
        )
    return findings


def _bundler_audit(cwd: str) -> list[dict[str, Any]]:
    if not shutil.which("bundler-audit"):
        return []
    _, stdout, _ = _run(["bundler-audit", "check", "--format", "json"], cwd)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    findings: list[dict[str, Any]] = []
    for r in data.get("results", []):
        adv = r.get("advisory") or {}
        gem = r.get("gem") or {}
        findings.append(
            {
                "file": "Gemfile.lock",
                "line": 0,
                "severity": _norm_severity(adv.get("criticality")),
                "category": "vulnerable_dependency",
                "source": "bundler-audit",
                "description": f"{gem.get('name')} {gem.get('version')} — {adv.get('id')}: {adv.get('title')}",
                "recommendation": (
                    f"Upgrade to {', '.join(adv.get('patched_versions') or []) or 'a patched version'}"
                ),
                "confidence": 1.0,
                "vuln_id": adv.get("id"),
                "package": gem.get("name"),
                "version": gem.get("version"),
            }
        )
    return findings


def py_dependency_audit_node(
    *,
    name: str = "dependency_audit",
    output_key: str = "dep_findings",
    cwd_key: str = "working_dir",
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a deterministic dependency-audit node.

    State input:
        `cwd_key` (default "working_dir"): repo root.

    State output:
        `output_key` (default "dep_findings"): list of finding dicts in
            the standard schema. Empty when no scanner is installed.
        "dep_scanners_run" / "dep_scanners_skipped": diagnostic lists.
    """

    async def run(state: dict[str, Any]) -> dict[str, Any]:
        cwd = state.get(cwd_key) or "."
        root = Path(cwd)

        plan: list[tuple[str, Callable[[str], list[dict[str, Any]]], bool]] = [
            (
                "pip-audit",
                _pip_audit,
                (root / "pyproject.toml").exists()
                or any(root.glob("requirements*.txt"))
                or (root / "Pipfile.lock").exists(),
            ),
            (
                "npm-audit",
                _npm_audit,
                (root / "package-lock.json").exists()
                or (root / "yarn.lock").exists(),
            ),
            ("govulncheck", _govulncheck, (root / "go.mod").exists()),
            ("cargo-audit", _cargo_audit, (root / "Cargo.lock").exists()),
            ("bundler-audit", _bundler_audit, (root / "Gemfile.lock").exists()),
        ]

        ran: list[str] = []
        skipped: list[str] = []
        all_findings: list[dict[str, Any]] = []

        for label, scanner, ecosystem_match in plan:
            if not ecosystem_match:
                continue
            findings = await asyncio.to_thread(scanner, str(root))
            if findings == [] and not _has_tool(label):
                skipped.append(label)
            else:
                ran.append(label)
                all_findings.extend(findings)

        return {
            output_key: all_findings,
            "dep_scanners_run": ran,
            "dep_scanners_skipped": skipped,
        }

    run.__name__ = name
    run.declared_outputs = (output_key, "dep_scanners_run", "dep_scanners_skipped")  # type: ignore[attr-defined]
    return run


def _has_tool(label: str) -> bool:
    return shutil.which({"pip-audit": "pip-audit", "npm-audit": "npm",
                         "govulncheck": "govulncheck", "cargo-audit": "cargo",
                         "bundler-audit": "bundler-audit"}.get(label, label)) is not None
