"""Python language skills."""

CLEAN_CODE = """\
# Python clean code

When you write or modify Python, follow these rules:

- Type-hint every public function and method. Prefer
  `from __future__ import annotations` so annotations
  don't evaluate at runtime.
- Keep functions short and single-purpose. If a function
  exceeds ~40 lines or three nesting levels, extract a
  helper.
- Name things for what they mean, not what they are.
  `parsed_records` over `data`, `is_authenticated` over
  `flag`.
- Prefer pure functions and explicit dependencies. Side
  effects belong at the edges of the program.
- Use dataclasses (`@dataclass(frozen=True)` when
  immutable) for structured records over ad-hoc dicts.
- Don't catch `Exception` broadly. Catch the narrowest
  type you can name and let the rest crash with a useful
  traceback.
- Don't write defensive code for situations that cannot
  occur given the call graph. Trust internal invariants.
- Don't add comments that restate the code. Comments
  explain *why* — a non-obvious constraint, a workaround,
  a subtle invariant.
- Match the surrounding codebase's style (formatter,
  import order, naming) over your own preferences.
- Use `pathlib.Path` over `os.path` string juggling.
- Use f-strings, not `.format()` or `%` formatting.
- Use `with` for any resource that has a `close()`.

When refactoring, change behavior in the smallest diff
that works. Avoid drive-by reformatting in the same change
as a logic edit — they're hard to review together."""

SECURITY = """\
# Python security

When writing or modifying Python, watch for these classes
of bug. If you spot one in code you're touching, fix it;
don't introduce new ones.

## Injection
- **Shell:** never pass user input to
  `subprocess.run(..., shell=True)` or `os.system`. Pass
  `argv` as a list and let the OS handle quoting.
- **SQL:** use parameterized queries
  (`cursor.execute("... WHERE id = %s", (user_id,))`).
  Never f-string user input into a query.
- **Path traversal:** when joining user-supplied filenames
  into a directory, resolve and verify the result stays
  under the base directory
  (`Path(base).resolve() in resolved.parents`).

## Deserialization
- Don't `pickle.loads()` data from untrusted sources —
  pickle executes arbitrary code on load.
- Use `yaml.safe_load`, never `yaml.load` without a
  trusted Loader.
- For JSON, prefer `json.loads`; if you need richer types,
  use a schema validator (pydantic, jsonschema) at the
  boundary.

## Secrets
- Never hardcode API keys, tokens, or passwords. Read
  from environment variables or a secret manager.
- Don't log request bodies, headers, or tracebacks that
  may contain credentials.
- Don't commit `.env` files. Verify `.gitignore` covers
  them before staging.

## Crypto
- Don't roll your own. Use `secrets` for random tokens,
  `hashlib` (SHA-256+) for hashing, and a vetted library
  (`cryptography`) for anything else.
- Use `secrets.compare_digest` for comparing tokens to
  defeat timing attacks.
- Hash passwords with `bcrypt`, `argon2`, or `scrypt` —
  never raw SHA.

## HTTP / network
- Always set timeouts on `requests`/`httpx` calls. A hung
  connection without a timeout will block forever.
- Verify TLS by default (`verify=True`); only disable for
  an explicit, justified reason.
- Validate redirects when chaining requests — don't
  auto-follow to arbitrary hosts with auth headers
  attached.

## Input validation
- Validate at trust boundaries (HTTP handlers, queue
  consumers, file ingestion). Internal callers can be
  trusted.
- Reject early with a clear error rather than coercing
  surprising inputs into something that "works".

If a change introduces a new boundary (new endpoint, new
ingestion path, new external call), pause and consider
what untrusted input could reach it."""
