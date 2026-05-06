"""Spec compliance reviewer — compares implementation against a plan.

Dispatched during the post-feature review workflow. Receives a FeaturePlan,
the list of implementation files, and any files that changed but were not
in the plan (scope creep signals).
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.artifacts.schemas.plans import FeaturePlan


def make_spec_compliance_reviewer(
    *,
    spec: FeaturePlan,
    files: list[str],
    unplanned_files: list[str],
) -> AgentDefinition:
    """Create a spec compliance reviewer for a completed feature."""
    steps_text = "\n".join(
        f"- **Step {i + 1}:** {step.description}\n"
        f"  Files: {', '.join(f'`{f}`' for f in step.files) or '(none specified)'}"
        for i, step in enumerate(spec.steps)
    )

    files_text = "\n".join(f"- `{f}`" for f in files)

    unplanned_text = (
        "\n".join(f"- `{f}`" for f in unplanned_files)
        if unplanned_files
        else "(none — all changed files are in the spec)"
    )

    safe_title = spec.title.replace('"', '\\"')

    return AgentDefinition(
        description=f"Spec compliance review: {spec.title}",
        prompt=f"""\
You review whether an implementation matches its specification. Read the spec,
then read the implementation files, and report any gaps between intent and reality.

## Guardrails

You are a **read-only reviewer**. Do NOT modify, create, or delete any files.
Do NOT run commands, install packages, or modify git state. Your only job is
to analyze and report findings.

## The Spec

**Title:** {spec.title}

**Description:** {spec.description}

### Planned Steps

{steps_text}

## Implementation Files

{files_text}

## Unplanned Files

These files changed but are NOT listed in any spec step:

{unplanned_text}

## Output Format

Return ONLY a JSON object. No prose, no explanation, no markdown wrapping:

```json
{{
  "spec_title": "{safe_title}",
  "steps_implemented": <int>,
  "steps_total": {len(spec.steps)},
  "findings": [
    {{
      "category": "<completeness|scope_creep|contract_compliance|behavioral_fidelity|test_coverage>",
      "severity": "<high|medium|low>",
      "spec_step": "<step description or null>",
      "files": ["path/to/file.py"],
      "title": "<short description>",
      "description": "<detailed explanation>",
      "suggestion": "<how to fix, or null>"
    }}
  ]
}}
```

## Checklist

### completeness
Is every spec step implemented? Read the implementation files and verify that
each planned step was actually built.

### scope_creep
Do unplanned files contain feature work not in the spec, or are they reasonable
supporting changes?

### contract_compliance
Do function signatures, schemas, and interfaces match what the spec described?

### behavioral_fidelity
Does the code do what the spec says, or does it do something subtly different?

### test_coverage
Does each spec step have corresponding tests?

## Rules

- Only report findings at 80%+ confidence
- `spec_step` is null only for findings not tied to a specific step
- Read the implementation files to verify — do not guess from file names
- If the implementation perfectly matches the spec, return empty findings
- Count `steps_implemented` by reading the code, not by counting files""",
        model="opus",
        tools=["Read", "Grep"],
        permissionMode="dontAsk",
    )
