"""Security audit agent — injection, secrets, unsafe deserialization, auth bypass, CSRF, session management.

Usage:
    python -m codemonkeys.agents.python_security_audit
    python -m codemonkeys.agents.python_security_audit --scope file --path src/auth.py
    python -m codemonkeys.agents.python_security_audit --scope repo
"""

from __future__ import annotations

from typing import Literal

from claude_agent_sdk import AgentDefinition

from codemonkeys.agents._scope import build_read_scope_context


def make_python_security_auditor(
    scope: Literal["file", "diff", "repo"] = "diff",
    path: str | None = None,
) -> AgentDefinition:
    """Create a security audit agent for injection, secrets, and auth issues."""
    tools: list[str] = ["Read", "Glob", "Grep"]

    method_intro, scope_tools, scope_exclusion = build_read_scope_context(
        scope, path, file_verb="audit"
    )
    tools.extend(scope_tools)

    return AgentDefinition(
        description=(
            "Use this agent to find security vulnerabilities in Python code: "
            "injection (SQL, NoSQL, command, LDAP, log, template), hardcoded secrets, "
            "unsafe deserialization, auth bypass, CSRF, session fixation, mass assignment, "
            "path traversal, insecure cookies."
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
- NoSQL injection — user-controlled dicts passed directly to pymongo /
  mongoengine `find()`, `update()`, or `aggregate()` without sanitizing
  operators (`$gt`, `$ne`, `$where`)
- Command injection via `subprocess` with `shell=True` and user input,
  or `os.system()` / `os.popen()`
- LDAP injection — user input concatenated into `python-ldap` or `ldap3`
  filter strings without `ldap.filter.escape_filter_chars()`
- Path traversal — user-controlled paths joined to filesystem operations
  without confining to a base dir
- SSRF — outbound requests built from user input without host allowlist,
  including via open redirect following
- Template injection — user input rendered via Jinja2 or similar as a
  template instead of data
- Log injection — user-controlled strings logged without newline
  sanitization, enabling log forging via embedded `\n` or ANSI escapes
- XXE — XML parsing with `xml.etree`, `lxml`, or `xml.dom` without
  disabling external entity resolution

### Authentication & authorization
- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without
  ownership check
- JWT: `alg=none` bypass, missing expiry validation, weak signing keys,
  secret in source
- Session fixation — session ID not regenerated after login (e.g.,
  Django `request.session` reused across auth boundary without
  `request.session.cycle_key()`, Flask without `session.regenerate()`)
- Missing session invalidation on password change or logout
- CSRF — state-changing endpoints (POST/PUT/DELETE) in cookie-auth apps
  that lack anti-CSRF tokens, or broad `@csrf_exempt` decorators
- Mass assignment — ORM objects created/updated with unfiltered request
  data (`Model.objects.create(**request.POST)`,
  `session.add(Model(**request.json))`) without explicit field allowlist

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

### Output & transport security
- Jinja2 templates with `autoescape=False`, or `|safe` filter /
  `Markup()` applied to user-controlled data
- Auth cookies set without `httponly=True`, `secure=True`, or
  `samesite='Lax'`/`'Strict'` — check `response.set_cookie()` and
  Django `SESSION_COOKIE_*` settings
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
- Do not pad the report. Zero findings is a valid result — it means
  the code is secure. Reporting a speculative finding to avoid an
  empty report is worse than returning nothing.

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

    from codemonkeys.runner import run_cli
    from codemonkeys.schemas import REVIEW_RESULT_SCHEMA

    parser = argparse.ArgumentParser(
        description="Security audit — injection, secrets, auth bypass"
    )
    parser.add_argument("--scope", choices=["file", "diff", "repo"], default="diff")
    parser.add_argument("--path", help="Narrow scope to this file or folder")
    args = parser.parse_args()

    prompt = (
        f"Audit Python source files under {args.path}."
        if args.path
        else "Audit the code for security vulnerabilities."
    )
    run_cli(
        make_python_security_auditor(scope=args.scope, path=args.path),
        prompt,
        REVIEW_RESULT_SCHEMA,
    )
