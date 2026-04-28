"""Type-check Python code with mypy and return findings as JSON."""

from __future__ import annotations

import sys

from agentpipe.nodes.base import ShellNode, Verbosity

_MYPY_SCRIPT = """\
import json, subprocess, sys

result = subprocess.run(
    [sys.executable, "-m", "mypy", "--output", "json", "--no-error-summary", "."],
    capture_output=True, text=True,
)
findings = []
for line in result.stdout.strip().splitlines():
    if not line.strip():
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    if obj.get("severity") == "note":
        continue
    severity = "HIGH" if obj.get("severity") == "error" else "MEDIUM"
    findings.append({
        "file": obj["file"],
        "line": obj["line"],
        "severity": severity,
        "category": obj.get("code", "type_error"),
        "source": "python_type_check",
        "description": obj["message"],
        "confidence": "high",
    })
high = sum(1 for f in findings if f["severity"] == "HIGH")
medium = sum(1 for f in findings if f["severity"] == "MEDIUM")
print(json.dumps({
    "findings": findings,
    "summary": {"high": high, "medium": medium, "low": 0},
}))
"""


class PythonTypeCheck(ShellNode):
    def __init__(
        self,
        *,
        timeout: float | None = None,
        verbosity: Verbosity = Verbosity.silent,
    ) -> None:
        super().__init__(
            name="python_type_check",
            command=[sys.executable, "-c", _MYPY_SCRIPT],
            check=False,
            timeout=timeout,
            verbosity=verbosity,
        )
