"""Language-agnostic security checklist loaded into file-reviewer agents."""

SECURITY_OBSERVATIONS = """\
## Security Review Checklist

Review the file for security vulnerabilities. Only report genuinely exploitable
findings with concrete attack scenarios.

### injection

- SQL via string concatenation or f-strings instead of parameterized queries
- NoSQL injection — user-controlled dicts passed to find/update without sanitizing operators
- Command injection via `subprocess` with `shell=True` and user input, or `os.system()`
- LDAP injection — user input concatenated into filter strings
- Path traversal — user-controlled paths without confining to a base directory
- SSRF — outbound requests built from user input without host allowlist
- Template injection — user input rendered as a template instead of data
- Log injection — user strings logged without newline sanitization
- XXE — XML parsing without disabling external entity resolution

### auth

- Auth bypass paths (missing middleware, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without ownership check
- JWT: `alg=none` bypass, missing expiry validation, weak signing keys
- Session fixation — session ID not regenerated after login
- CSRF — state-changing endpoints without anti-CSRF tokens
- Mass assignment — ORM objects created with unfiltered request data

### secrets

- Hardcoded keys, tokens, passwords, connection strings
- Weak password hashing (raw SHA, MD5 instead of bcrypt/argon2)
- `random` module used for security-critical values (use `secrets`)
- TLS verification disabled (`verify=False`)
- Non-constant-time token comparison (use `hmac.compare_digest`)

### deserialization

- `pickle.loads()` / `yaml.load()` on untrusted input (use `yaml.safe_load()`)
- `eval()` / `exec()` with user-controlled strings

### output_security

- Jinja2 templates with `autoescape=False`
- Auth cookies without `httponly=True`, `secure=True`, `samesite`
- PII/credentials in logs or error responses

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Code quality issues (code-quality checklist owns these)
- Dependency vulnerabilities (pip-audit owns these)
- Test failures (test runner owns these)
- Denial of service (out of scope)"""
