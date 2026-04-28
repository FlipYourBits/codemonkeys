"""Type-check Python code with mypy and return findings as JSON."""

from __future__ import annotations

import sys

from pydantic import BaseModel, Field

from agentpipe.nodes.base import ShellNode, Verbosity


class TypeCheckFinding(BaseModel):
    file: str = Field(examples=["foo.py"])
    line: int = Field(examples=[10])
    severity: str = Field(examples=["HIGH"])
    category: str = Field(examples=["type_error"])
    source: str = Field(examples=["python_type_check"])
    description: str = Field(examples=["Incompatible types in assignment."])
    confidence: str = Field(examples=["high"])


class TypeCheckOutput(BaseModel):
    findings: list[TypeCheckFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict, examples=[{"high": 0, "medium": 0, "low": 0}]
    )

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
            output=TypeCheckOutput,
            check=False,
            timeout=timeout,
            verbosity=verbosity,
        )
