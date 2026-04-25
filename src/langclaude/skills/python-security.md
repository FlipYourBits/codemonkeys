# Python security

When writing or modifying Python, watch for these classes of bug. If you spot one in code you're touching, fix it; don't introduce new ones.

## Injection
- **Shell:** never pass user input to `subprocess.run(..., shell=True)` or `os.system`. Pass `argv` as a list and let the OS handle quoting.
- **SQL:** use parameterized queries (`cursor.execute("... WHERE id = %s", (user_id,))`). Never f-string user input into a query.
- **Path traversal:** when joining user-supplied filenames into a directory, resolve and verify the result stays under the base directory (`Path(base).resolve() in resolved.parents`).

## Deserialization
- Don't `pickle.loads()` data from untrusted sources — pickle executes arbitrary code on load.
- Use `yaml.safe_load`, never `yaml.load` without a trusted Loader.
- For JSON, prefer `json.loads`; if you need richer types, use a schema validator (pydantic, jsonschema) at the boundary.

## Secrets
- Never hardcode API keys, tokens, or passwords. Read from environment variables or a secret manager.
- Don't log request bodies, headers, or tracebacks that may contain credentials.
- Don't commit `.env` files. Verify `.gitignore` covers them before staging.

## Crypto
- Don't roll your own. Use `secrets` for random tokens, `hashlib` (SHA-256+) for hashing, and a vetted library (`cryptography`) for anything else.
- Use `secrets.compare_digest` for comparing tokens to defeat timing attacks.
- Hash passwords with `bcrypt`, `argon2`, or `scrypt` — never raw SHA.

## HTTP / network
- Always set timeouts on `requests`/`httpx` calls. A hung connection without a timeout will block forever.
- Verify TLS by default (`verify=True`); only disable for an explicit, justified reason.
- Validate redirects when chaining requests — don't auto-follow to arbitrary hosts with auth headers attached.

## Input validation
- Validate at trust boundaries (HTTP handlers, queue consumers, file ingestion). Internal callers can be trusted.
- Reject early with a clear error rather than coercing surprising inputs into something that "works".

If a change introduces a new boundary (new endpoint, new ingestion path, new external call), pause and consider what untrusted input could reach it.
