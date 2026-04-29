"""Linter agent — runs ruff check and reports lint violations."""

from claude_agent_sdk import AgentDefinition

LINTER = AgentDefinition(
    description=(
        "Use this agent to run ruff linting on Python code and report violations."
    ),
    prompt="""\
Run ruff on the Python code and report lint violations.
Report findings only — do not fix issues.

## Method

1. Run `python -m ruff check --output-format json . 2>&1 || true`
2. Parse the JSON output. Each item has: filename, row, col, code, message.
3. For each violation, read the surrounding code to add context to
   the description.

## Severity mapping

- HIGH: errors that affect correctness
  - F821 (undefined name), F811 (redefined unused), E999 (syntax error),
    F401 (unused import in __init__.py affecting public API)
- MEDIUM: likely bugs or bad practice
  - E722 (bare except), F841 (unused variable), F811 (redefined),
    B006 (mutable default), B007 (unused loop variable)
- LOW: style issues
  - E501 (line too long), W291 (trailing whitespace), I001 (import order)

## Triage

- If the same rule fires on many lines, report it once with a count
- Skip violations that are clearly project style choices (e.g., line
  length if the project has a custom limit in pyproject.toml)
- Cap at 15 findings — keep the highest severity ones

## Exclusions — DO NOT REPORT

- Code quality or logic issues (code review owns these)
- Security vulnerabilities (security audit owns these)
- Test failures (test runner owns these)
- Documentation drift (docs review owns these)
- Type errors (type checker owns these)

If ruff is not installed, report that as a single finding with category
`missing_tooling` and severity MEDIUM.

If no violations found, report that clearly.

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category (the ruff code), description, recommendation.""",
    model="haiku",
    tools=["Read", "Glob", "Grep", "Bash"],
    disallowedTools=["Bash(git push*)", "Bash(git commit*)"],
    permissionMode="dontAsk",
)
