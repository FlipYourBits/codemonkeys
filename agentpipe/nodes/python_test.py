"""Run pytest and analyze failures."""

from __future__ import annotations

from agentpipe.models import SONNET_4_6
from agentpipe.nodes.base import ClaudeAgentNode

_SKILL = """\
# Test analysis

You run the project's test suite and analyze failures.
Report findings only — do not fix issues.

## Method

1. Run `python -m pytest -x -q --tb=short --no-header` to
   execute the test suite. If the project has pytest config
   in pyproject.toml, those settings apply automatically.
2. For each failure: read the failing test and the code
   under test to identify the root cause.
3. Report each failure as a finding with the root cause
   and a concrete recommended fix.

## Categories

### `test_failure`
- Assertion failure caused by a bug in the code under test
- Regression — previously passing test now fails

### `test_error`
- Test infrastructure issues (missing fixtures, import
  errors, configuration problems)

## Triage

- Skip expected failures (xfail) and skipped tests.
- If the same root cause produces multiple test failures,
  report it once with the most informative test.

## Exclusions — DO NOT REPORT

- Code quality or style issues (code review owns these)
- Security vulnerabilities (security audit owns these)
- Documentation drift (docs review owns these)
- Dependency vulnerabilities (dependency audit owns these)

## Output

Final reply must be a single fenced JSON block matching
this schema and nothing after it:

```json
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "test_failure",
      "source": "python_test",
      "description": "One-sentence statement of the failure.",
      "recommendation": "What to change to fix it.",
      "confidence": "high"
    }
  ],
  "summary": {
    "tests_run": 50,
    "tests_passed": 48,
    "tests_failed": 2,
    "tests_skipped": 0,
    "tests_xfailed": 0,
    "high": 1,
    "medium": 1,
    "low": 0
  }
}
```

Severity guide:
- **HIGH**: test failure from a bug that affects production
- **MEDIUM**: edge case regression or minor breakage
- **LOW**: flaky test or configuration issue

If all tests pass, return an empty `findings` array."""


class PythonTest(ClaudeAgentNode):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("model", SONNET_4_6)
        super().__init__(
            name="python_test",
            system_prompt=_SKILL,
            prompt_template="Run the test suite and analyze any failures.",
            allow=[
                "Read",
                "Glob",
                "Grep",
                "Bash(git diff*)",
                "Bash(git log*)",
                "Bash(git show*)",
                "Bash(git blame*)",
                "Bash(git status*)",
                "Bash(git ls-files*)",
                "Bash(pytest*)",
                "Bash(python -m pytest*)",
                "Bash(python -m unittest*)",
            ],
            deny=[],
            on_unmatched="deny",
            **kwargs,
        )
