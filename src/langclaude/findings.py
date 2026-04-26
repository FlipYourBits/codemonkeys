"""Findings parsing and filtering — the lingua franca for review nodes.

Review nodes (security_audit, future code_review, perf review, etc.) emit a
JSON report containing a `findings` list. Each finding dict has at least:

    {
        "file": str,
        "line": int,
        "severity": "HIGH" | "MEDIUM" | "LOW",
        "category": str,
        "description": str,
        "recommendation": str,
        "confidence": float,           # 0..1
        "source": str,                 # which scanner/node produced it
        # extra fields are passed through verbatim
    }

The fixer node consumes this shape regardless of which review produced it.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
    re.DOTALL,
)

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def parse_findings(payload: Any) -> list[dict[str, Any]]:
    """Extract a flat list of finding dicts from review-node output.

    Accepts:
        - list[dict]: returned as-is (filtered to dicts).
        - dict with "findings": its findings list.
        - dict that looks like a single finding (has "file"): wrapped.
        - str: looks for a fenced ```json ... ``` block, falls back to
          parsing the whole string as JSON.

    Returns an empty list when nothing parseable is found — never raises.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [f for f in payload if isinstance(f, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("findings"), list):
            return [f for f in payload["findings"] if isinstance(f, dict)]
        if "file" in payload:
            return [payload]
        return []
    if not isinstance(payload, str):
        return []

    match = _FENCE_RE.search(payload)
    candidate = match.group(1) if match else payload.strip()
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    return parse_findings(obj)


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicates keyed by (file, line, category). First wins."""
    seen: set[tuple[Any, Any, Any]] = set()
    out: list[dict[str, Any]] = []
    for f in findings:
        key = (f.get("file"), f.get("line"), f.get("category"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def passes_threshold(
    finding: dict[str, Any],
    *,
    severity_threshold: str = "MEDIUM",
    confidence_threshold: float = 0.8,
) -> bool:
    """True if the finding meets both severity and confidence thresholds."""
    sev = str(finding.get("severity") or "").upper()
    try:
        conf = float(finding.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    sev_min = _SEVERITY_ORDER.get(severity_threshold.upper(), 1)
    sev_val = _SEVERITY_ORDER.get(sev, -1)
    return sev_val >= sev_min and conf >= confidence_threshold
