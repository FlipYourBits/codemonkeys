"""Security audit of Python source."""

from __future__ import annotations

from typing import Literal

from agentpipe.models import OPUS_4_6
from agentpipe.nodes.base import ClaudeAgentNode

_SKILL = """\
# Security audit

Security audit focused on high-confidence, exploitable
Python vulnerabilities — not theoretical or stylistic
issues. Better to miss speculative findings than flood
the report with false positives.

Report findings only — do not fix issues.

## Scope

{scope_section}

## Method

{method_intro} Trace data flow from untrusted inputs (HTTP
handlers, CLI args, env vars, queue consumers, file
ingest) to sinks.

### Injection
- SQL via string concatenation or interpolation into raw
  queries instead of parameterized queries
- Command injection via `subprocess` with `shell=True` and
  user input, or `os.system()` / `os.popen()`
- Path traversal — user-controlled paths joined to
  filesystem operations without confining to a base dir
- SSRF — outbound requests built from user input without
  host allowlist, including via open redirect following
- Template injection — user input rendered via Jinja2 or
  similar as a template instead of data
- XXE — XML parsing with `xml.etree`, `lxml`, or
  `xml.dom` without disabling external entity resolution

### Authentication & authorization
- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only,
  missing on API)
- IDOR — operations that trust a client-supplied resource
  ID without ownership check
- JWT: `alg=none` bypass, missing expiry validation,
  weak signing keys, secret in source

### Secrets & crypto
- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of bcrypt /
  argon2 / scrypt)
- Weak crypto primitives (DES, RC4, ECB mode)
- `random` module used for security-critical values (use
  `secrets` instead)
- TLS verification disabled (`verify=False`)
- Non-constant-time token comparison (use
  `hmac.compare_digest`)
- Files created with world-readable permissions (e.g.
  `0o666`) containing secrets or credentials

### Unsafe deserialization & code execution
- `pickle.loads()` / `yaml.load()` on untrusted input
  (use `yaml.safe_load()`)
- `eval()` / `exec()` with user-controlled strings
- `__import__()` or `importlib` with user input

### Data exposure
- PII / credentials in logs, error responses, or debug
  output
- Verbose stack traces returned to clients
- Missing redaction in telemetry
- Overly broad CORS with credentials

### Other
- Race conditions on auth or financial state (TOCTOU)
- Missing rate limits on auth endpoints (only flag if it
  enables credential stuffing)

## Triage

- Drop duplicates — keep the finding with the strongest
  evidence.
- Only report findings you believe are genuinely
  exploitable. If you can't describe a concrete attack
  scenario, leave it out.

## Exclusions — DO NOT REPORT

- Code quality, complexity, or maintainability concerns
  (code review owns these)
- Dependency vulnerabilities (dependency audit owns these)
- Test failures or missing tests (test node owns these)
- Documentation drift (docs review owns these)
- Denial of service or resource exhaustion
- Lack of input validation on fields with no security
  impact
- Performance issues{exclusion_extra}

## Output

Final reply must be a single fenced JSON block matching
this schema and nothing after it:

```json
{{
  "findings": [
    {{
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "command_injection",
      "source": "python_security_audit",
      "description": "User input passed to subprocess
        with shell=True.",
      "exploit_scenario": "Attacker injects shell commands
        via the name parameter.",
      "recommendation": "Use subprocess.run() with a list
        argument instead of shell=True.",
      "confidence": "high"
    }}
  ],
  "summary": {{
    "files_reviewed": 12,
    "high": 1,
    "medium": 0,
    "low": 0
  }}
}}
```

`confidence`: "high", "medium", or "low". Only include
findings where confidence is "high" or "medium".

Severity guide:
- **HIGH**: directly exploitable — RCE, auth bypass,
  data breach, account takeover
- **MEDIUM**: exploitable under specific but realistic
  conditions
- **LOW**: defense-in-depth or limited-impact issues

If there are no findings, return an empty `findings`
array."""


class PythonSecurityAudit(ClaudeAgentNode):
    def __init__(
        self,
        *,
        scope: Literal["diff", "full_repo"] = "diff",
        base_ref: str = "main",
        **kwargs,
    ) -> None:
        kwargs.setdefault("model", OPUS_4_6)

        if scope == "diff":
            scope_section = (
                "Diff mode: only review changes between the base ref and\n"
                "`HEAD`. Do not flag pre-existing issues outside the diff."
            )
            method_intro = (
                "Run the git diff command from the prompt and read every\nchanged file."
            )
            exclusion_extra = "\n- Pre-existing issues outside the diff"
            prompt = (
                f"Report only vulnerabilities introduced by the diff against {base_ref}. "
                f"Start by running `git diff {base_ref}...HEAD` and reading the changed files."
            )
        else:
            scope_section = (
                "Full repo: audit all Python source files in the\nrepository."
            )
            method_intro = (
                "List all Python source files with `git ls-files '*.py'`\n"
                "and read each one."
            )
            exclusion_extra = ""
            prompt = (
                "Audit all Python source files in the repository for security vulnerabilities. "
                "Start by running `git ls-files '*.py'` and reading each file."
            )

        super().__init__(
            name="python_security_audit",
            system_prompt=_SKILL.format(
                scope_section=scope_section,
                method_intro=method_intro,
                exclusion_extra=exclusion_extra,
            ),
            prompt_template=prompt,
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
            ],
            deny=[],
            on_unmatched="deny",
            **kwargs,
        )
