"""Rust language skills."""

CLEAN_CODE = """\
# Rust clean code

When you write or modify Rust, follow these rules:

- Let the type system do the work. Prefer newtypes, enums,
  and `Option`/`Result` over stringly-typed data or
  sentinel values.
- Keep functions short and single-purpose. If a function
  exceeds ~40 lines or three nesting levels, extract a
  helper.
- Name things for what they mean. `parsed_records` over
  `data`, `is_authenticated` over `flag`.
- Prefer returning `Result<T, E>` over panicking. Reserve
  `unwrap()`/`expect()` for cases where the invariant is
  provably upheld or in tests.
- Use `?` for error propagation. Define domain error types
  with `thiserror` or map errors at the boundary.
- Prefer iterators and combinators (`.map`, `.filter`,
  `.collect`) over manual index loops when the intent is
  clearer.
- Derive `Debug`, `Clone`, and other standard traits when
  useful. Derive `Default` when a zero/empty state is
  meaningful.
- Use `#[must_use]` on functions whose return value should
  not be silently ignored.
- Prefer borrowing over cloning. Clone only when ownership
  transfer is needed or the cost is negligible.
- Use `impl Trait` in argument position for simple generic
  bounds. Use explicit generics when bounds get complex or
  trait objects when dynamic dispatch is needed.
- Keep `unsafe` blocks minimal and document the safety
  invariant they rely on.
- Match the surrounding codebase's style (formatter,
  import order, naming) over your own preferences.

When refactoring, change behavior in the smallest diff
that works. Avoid drive-by reformatting in the same change
as a logic edit."""

SECURITY = """\
# Rust security

When writing or modifying Rust, watch for these classes of
bug. If you spot one in code you're touching, fix it;
don't introduce new ones.

## Unsafe code
- Minimize `unsafe` blocks. Every `unsafe` block must have
  a `// SAFETY:` comment explaining why the invariant
  holds.
- Never dereference raw pointers from untrusted input
  without validation.
- Audit FFI boundaries — C functions don't uphold Rust's
  aliasing or lifetime rules. Wrap them in safe
  abstractions.

## Injection
- **Command injection:** never pass user input to
  `std::process::Command` with `shell=true` semantics.
  Use `.arg()` to pass arguments individually.
- **SQL:** use parameterized queries via `sqlx`, `diesel`,
  or equivalent. Never format user input into query
  strings.
- **Path traversal:** when joining user-supplied filenames,
  canonicalize and verify the result stays under the base
  directory.

## Memory and concurrency
- Prefer `Arc<Mutex<T>>` or channels over raw shared
  state. If using `unsafe` concurrency primitives, prove
  the absence of data races.
- Avoid `mem::transmute` unless absolutely necessary —
  prefer safe conversions (`From`/`Into`, `as`).
- Validate buffer sizes before indexing. Prefer `.get()`
  over direct indexing when the index comes from external
  input.

## Deserialization
- Validate deserialized input at the boundary. Use `serde`
  with strict schemas — don't trust shape assumptions from
  external JSON/TOML/etc.
- Be cautious with `#[serde(deny_unknown_fields)]` vs
  permissive defaults depending on the trust level of the
  source.

## Secrets
- Never hardcode API keys, tokens, or passwords. Read
  from environment variables or a secret manager.
- Use `zeroize` for sensitive data in memory (keys,
  passwords) to clear on drop.
- Don't log request bodies, headers, or tracebacks that
  may contain credentials.

## Crypto
- Use vetted crates (`ring`, `rustls`, `argon2`,
  `chacha20poly1305`). Don't implement crypto primitives.
- Use constant-time comparison for tokens and MACs.
- Hash passwords with argon2, scrypt, or bcrypt — never
  raw SHA.

## HTTP / network
- Always set timeouts on HTTP clients (`reqwest`, `hyper`).
  A hung connection without a timeout will block the task.
- Validate TLS certificates by default. Only disable for
  an explicit, justified reason.
- Validate redirects — don't auto-follow to arbitrary
  hosts with auth headers attached.

## Input validation
- Validate at trust boundaries (HTTP handlers, message
  queue consumers, file ingestion). Internal callers can
  be trusted.
- Reject early with a clear error rather than coercing
  surprising inputs.
- Use Rust's type system to make invalid states
  unrepresentable where possible.

If a change introduces a new boundary (new endpoint, new
ingestion path, new external call), pause and consider
what untrusted input could reach it."""
