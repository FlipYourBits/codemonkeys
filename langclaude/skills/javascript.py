"""JavaScript / TypeScript language skills."""

CLEAN_CODE = """\
# JavaScript clean code

When you write or modify JavaScript/TypeScript/React,
follow these rules:

- Use TypeScript when the project uses it. Add explicit
  return types to exported functions. Prefer `interface`
  for object shapes, `type` for unions and intersections.
- Prefer `const` over `let`. Never use `var`.
- Use arrow functions for callbacks and short helpers. Use
  `function` declarations for top-level named functions
  that benefit from hoisting.
- Keep functions short and single-purpose. If a function
  exceeds ~40 lines or three nesting levels, extract a
  helper.
- Name things for what they mean. `fetchUserProfile` over
  `getData`, `isAuthenticated` over `flag`.
- Prefer immutability — spread/destructure over mutation.
  Use `Object.freeze` or `as const` when appropriate.
- Use `async`/`await` over raw `.then()` chains. Always
  handle rejections — unhandled promise rejections crash
  Node processes.
- Prefer `===` and `!==`. Never use `==` or `!=` except
  when intentionally checking `null`/`undefined` with
  `== null`.
- Use template literals over string concatenation.
- Use optional chaining (`?.`) and nullish coalescing
  (`??`) over verbose null checks.
- Prefer `Map`/`Set` over plain objects when keys are
  dynamic or non-string.
- In React: keep components focused. Extract hooks for
  reusable state logic. Prefer controlled components.
  Memoize (`useMemo`, `useCallback`) only when profiling
  shows a need — premature memoization adds complexity.
- Match the surrounding codebase's style (formatter,
  import order, naming) over your own preferences.

When refactoring, change behavior in the smallest diff
that works. Avoid drive-by reformatting in the same change
as a logic edit."""

SECURITY = """\
# JavaScript security

When writing or modifying JavaScript/TypeScript, watch for
these classes of bug. If you spot one in code you're
touching, fix it; don't introduce new ones.

## Injection
- **XSS:** never insert user input into the DOM via
  `innerHTML`, `outerHTML`, or `document.write`. Use
  `textContent` or a framework's auto-escaping (React JSX,
  Vue templates). Sanitize if raw HTML is unavoidable
  (`DOMPurify`).
- **SQL:** use parameterized queries or an ORM's query
  builder. Never template user input into query strings.
- **Command injection:** never pass user input to
  `child_process.exec`. Use `execFile` or `spawn` with an
  argv array.
- **Path traversal:** when joining user-supplied filenames,
  resolve and verify the result stays under the base
  directory
  (`path.resolve(base, input).startsWith(path.resolve(base))`).

## Deserialization
- Don't `eval()` or `new Function()` with untrusted input.
- Validate JSON payloads at the boundary with a schema
  validator (zod, ajv, joi) — don't trust shape
  assumptions.
- Watch for prototype pollution when merging objects from
  external input. Use `Object.create(null)` or a safe
  merge utility.

## Secrets
- Never hardcode API keys, tokens, or passwords. Read
  from environment variables or a secret manager.
- Don't log request bodies, headers, or tracebacks that
  may contain credentials.
- Don't commit `.env` files. Verify `.gitignore` covers
  them before staging.
- Never expose secrets in client-side bundles — use
  server-side environment variables and API routes.

## Crypto
- Use the Web Crypto API or `crypto` module from Node —
  don't roll your own.
- Use `crypto.timingSafeEqual` for comparing tokens to
  defeat timing attacks.
- Hash passwords with bcrypt, scrypt, or argon2 — never
  raw SHA.

## HTTP / network
- Always set timeouts on fetch/axios calls. A hung
  connection without a timeout will block the event loop.
- Validate `Origin`/`Referer` headers or use CSRF tokens
  for state-changing requests.
- Set `SameSite`, `HttpOnly`, and `Secure` flags on
  cookies.
- Validate redirects — don't auto-follow to arbitrary
  hosts with auth headers attached.

## Input validation
- Validate at trust boundaries (HTTP handlers, message
  queue consumers, file ingestion). Internal callers can
  be trusted.
- Reject early with a clear error rather than coercing
  surprising inputs.
- Use `Content-Security-Policy` headers to limit what
  scripts can execute in the browser.

If a change introduces a new boundary (new endpoint, new
ingestion path, new external call), pause and consider
what untrusted input could reach it."""
