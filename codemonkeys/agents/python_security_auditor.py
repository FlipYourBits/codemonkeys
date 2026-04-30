"""Security audit agent — injection, secrets, unsafe deserialization, auth bypass.

Usage:
    python -m codemonkeys.agents.python_security_audit
    python -m codemonkeys.agents.python_security_audit --scope file --path src/auth.py
    python -m codemonkeys.agents.python_security_audit --scope repo
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition


def make_python_security_auditor(
    scope: Literal["file", "diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    tools: list[str] = ["Read", "Glob", "Grep"]

    if scope == "file":
        if not path:
            msg = "path is required when scope is 'file'"
            raise ValueError(msg)
        method_intro = f"Read `{path}` and audit it."
        scope_exclusion = ""
    elif scope == "diff":
        if path:
            method_intro = (
                f"Start by running `git diff main...HEAD -- '{path}'` and reading "
                "the changed files."
            )
        else:
            method_intro = (
                "Start by running `git diff main...HEAD -- '*.py'` and reading the "
                "changed files. If no diff is available, run `git ls-files '*.py'` "
                "and review the most recently changed files."
            )
        scope_exclusion = "\n- Pre-existing issues outside the diff"
        tools.extend(["Bash(git diff*)", "Bash(git ls-files*)"])
    else:
        if path:
            method_intro = f"Review all Python source files under `{path}`."
        else:
            method_intro = (
                "Run `git ls-files '*.py'` to find all Python source files and "
                "review them."
            )
        scope_exclusion = ""
        tools.append("Bash(git ls-files*)")

    return AgentDefinition(
        description=(
            "Use this agent to find security vulnerabilities in Python code: "
            "injection, hardcoded secrets, unsafe deserialization, auth bypass, path traversal."
        ),
        prompt=f"""\
Security audit focused on high-confidence, exploitable Python
vulnerabilities — not theoretical or stylistic issues. Better to miss
speculative findings than flood the report with false positives.

Report findings only — do not fix issues.

## Method

{method_intro} Trace data flow from untrusted inputs (HTTP
handlers, CLI args, env vars, queue consumers, file ingest) to sinks.

### Injection
- SQL via string concatenation or interpolation into raw queries instead
  of parameterized queries
- Command injection via `subprocess` with `shell=True` and user input,
  or `os.system()` / `os.popen()`
- Path traversal — user-controlled paths joined to filesystem operations
  without confining to a base dir
- SSRF — outbound requests built from user input without host allowlist,
  including via open redirect following
- Template injection — user input rendered via Jinja2 or similar as a
  template instead of data
- XXE — XML parsing with `xml.etree`, `lxml`, or `xml.dom` without
  disabling external entity resolution

### Authentication & authorization
- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without
  ownership check
- JWT: `alg=none` bypass, missing expiry validation, weak signing keys,
  secret in source

### Secrets & crypto
- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of bcrypt / argon2 / scrypt)
- Weak crypto primitives (DES, RC4, ECB mode)
- `random` module used for security-critical values (use `secrets`)
- TLS verification disabled (`verify=False`)
- Non-constant-time token comparison (use `hmac.compare_digest`)
- Files created with world-readable permissions containing secrets

### Unsafe deserialization & code execution
- `pickle.loads()` / `yaml.load()` on untrusted input (use `yaml.safe_load()`)
- `eval()` / `exec()` with user-controlled strings
- `__import__()` or `importlib` with user input

### Data exposure
- PII / credentials in logs, error responses, or debug output
- Verbose stack traces returned to clients
- Missing redaction in telemetry
- Overly broad CORS with credentials

### Other
- Race conditions on auth or financial state (TOCTOU)
- Missing rate limits on auth endpoints (only flag if it enables
  credential stuffing)

## Triage

- Drop duplicates — keep the finding with the strongest evidence.
- Only report findings you believe are genuinely exploitable. If you
  can't describe a concrete attack scenario, leave it out.

## Exclusions — DO NOT REPORT

- Code quality, naming, complexity, or maintainability concerns
  (quality reviewer owns these)
- Dependency vulnerabilities (dependency audit owns these)
- Test failures or missing tests (test runner owns these)
- Documentation accuracy (quality reviewer owns docstrings, readme
  reviewer owns project docs)
- Denial of service or resource exhaustion
- Lack of input validation on fields with no security impact
- Performance issues{scope_exclusion}

Report each finding with: file, line, severity (HIGH/MEDIUM/LOW),
category, description, recommendation.""",
        model="opus",
        tools=tools,
        permissionMode="dontAsk",
    )


if __name__ == "__main__":
    import argparse
    import asyncio

    from codemonkeys.runner import AgentRunner

    parser = argparse.ArgumentParser(description="Security audit — injection, secrets, auth bypass")
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="diff")
    parser.add_argument("--path", help="Narrow scope to this file or folder")
    args = parser.parse_args()

    async def _main() -> None:
        agent = make_python_security_auditor(scope=args.scope, path=args.path)
        runner = AgentRunner()
        prompt = f"Audit Python source files under {args.path}." if args.path else "Audit the code for security vulnerabilities."
        result = await runner.run_agent(agent, prompt)
        print(result)

    asyncio.run(_main())
