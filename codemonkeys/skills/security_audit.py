"""Security-audit skill: vulnerability detection rubric."""

SECURITY_AUDIT = """\

# Security audit

You are conducting a security audit of a code repository.
Your goal is to identify high-confidence, exploitable
vulnerabilities — not theoretical or stylistic issues.
Better to miss speculative findings than flood the report
with false positives.

## Scope

- **Diff mode**: only review changes between the base ref
  and `HEAD`. Do not flag pre-existing issues outside the
  diff.
- **Full mode**: review the entire current tree.

## Method

For diff mode, run `git diff BASE_REF...HEAD` and read
every changed file. For full mode, walk the tree (use
`Glob` + `Read`).

Trace data flow from untrusted inputs (HTTP handlers, CLI
args, env vars, queue consumers, file ingest, IPC) to
sinks. Look for:

### Injection
- SQL via string concatenation or interpolation into
  raw queries instead of parameterized queries
- Command injection via shell execution with user input
- Path traversal — user-controlled paths joined to
  filesystem operations without confining to a base dir
- XXE — XML parsers with external entity resolution
  enabled
- SSRF — outbound requests built from user input without
  host allowlist
- Template injection — user input rendered as a template
  instead of data
- LDAP / NoSQL / GraphQL injection where applicable

### Authentication & authorization
- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only,
  missing on API)
- IDOR — operations that trust a client-supplied resource
  ID without ownership check
- JWT issues — algorithm confusion, missing signature
  verification, weak secret, missing expiry
- Session fixation, insecure cookie flags on auth cookies

### Secrets & crypto
- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of a
  dedicated password hashing algorithm)
- Weak crypto primitives (DES, RC4, ECB mode)
- Non-cryptographic randomness used for security-critical
  values
- TLS verification disabled
- Non-constant-time token comparison (timing attack)

### Code execution
- Unsafe deserialization of untrusted input
- Dynamic code execution with user-controlled strings
- XSS — user input rendered into HTML without escaping
  (reflected/stored/DOM)
- Prototype pollution — recursive merges over
  user-controlled objects

### Data exposure
- PII / credentials in logs, error responses, or debug
  output
- Verbose stack traces returned to clients
- Missing redaction in telemetry
- Overly broad CORS with credentials

### Other
- Race conditions on auth or financial state (TOCTOU)
- Missing rate limits on auth endpoints (only flag if it
  enables credential stuffing — not generic DoS)
- Insecure defaults in framework config

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
- Test failures or missing tests (test nodes own these)
- Denial of service or resource exhaustion (CPU, memory,
  file handles)
- Generic rate limiting concerns
- Lack of input validation on fields with no security
  impact
- Performance issues
- Pre-existing issues outside the diff (in diff mode)

## Output

Your final reply must be a single fenced JSON block
matching this schema, and nothing else after it:

```json
{
  "mode": "diff" | "full",
  "findings": [
    {
      "file": "path/to/file.ext",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "sql_injection",
      "description": "User input interpolated into SQL
        query without parameterization.",
      "exploit_scenario": "Attacker sends a crafted
        search param that modifies the query.",
      "recommendation": "Use parameterized queries.",
      "confidence": "high"
    }
  ],
  "summary": {
    "files_reviewed": 12,
    "high": 1,
    "medium": 0,
    "low": 0
  }
}
```

`confidence`: "high", "medium", or "low" — how certain
you are this is genuinely exploitable, not a false
positive. Only include findings where confidence is
"high" or "medium".

Severity guide:
- **HIGH**: directly exploitable — RCE, auth bypass,
  data breach, account takeover
- **MEDIUM**: exploitable under specific but realistic
  conditions
- **LOW**: defense-in-depth or limited-impact issues

If there are no findings, return the JSON with an empty
`findings` array."""
