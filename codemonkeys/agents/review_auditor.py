"""Review auditor agent — verifies reviewer behavior against its mandate."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from codemonkeys.core.types import AgentDefinition

Verdict = Literal["pass", "warn", "fail"]
Category = Literal[
    "file_coverage",
    "tool_compliance",
    "finding_quality",
    "instruction_compliance",
    "hallucination_risk",
]
Severity = Literal["high", "medium", "low", "info"]


class AuditFinding(BaseModel):
    category: Category
    severity: Severity
    title: str
    description: str
    suggestion: str | None = None


class ReviewAudit(BaseModel):
    verdict: Verdict
    findings: list[AuditFinding]
    summary: str


def make_review_auditor(
    trace: str,
    findings_json: str,
    reviewer_name: str,
    reviewer_model: str,
    reviewer_tools: str,
    reviewer_prompt: str,
    *,
    model: str = "sonnet",
) -> AgentDefinition:
    """Audits a reviewer agent's work to verify behavior compliance."""
    return AgentDefinition(
        name=f"auditor:{reviewer_name}",
        model=model,
        system_prompt=f"""\
You are a review auditor. Analyze the trace below and produce an audit verdict in one pass.

IMPORTANT: The event trace below may show truncated file contents and thinking text.
This truncation is ONLY in this audit view — the reviewer saw the full content.
Do NOT flag truncation as a coverage or hallucination issue.

## Reviewer Configuration

- **Agent:** {reviewer_name}
- **Model:** {reviewer_model}
- **Allowed tools:** {reviewer_tools}

### Reviewer's System Prompt

{reviewer_prompt}

## Event Trace

{trace}

## Structured Output (Findings)

{findings_json}

## Checks

1. **file_coverage** — Did it Read every assigned file?
2. **tool_compliance** — Only used {reviewer_tools}? Any denied calls?
3. **finding_quality** — Findings specific and backed by trace evidence?
4. **instruction_compliance** — Followed its system prompt?
5. **hallucination_risk** — References code/lines not in tool results?

## Output Rules

- **verdict** must be exactly one of: `pass`, `warn`, `fail`
- **category** must be exactly one of: `file_coverage`, `tool_compliance`, `finding_quality`, `instruction_compliance`, `hallucination_risk`
- **severity** must be exactly one of: `high`, `medium`, `low`, `info`
- Include a **suggestion** for each finding (how to fix the reviewer's behavior)
- Produce your verdict immediately. Do not request additional information.""",
        tools=[],
        output_schema=ReviewAudit,
    )
