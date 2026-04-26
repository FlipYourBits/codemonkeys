# Rust clean code

When you write or modify Rust, follow these rules:

- Let the type system do the work. Prefer newtypes, enums, and `Option`/`Result` over stringly-typed data or sentinel values.
- Keep functions short and single-purpose. If a function exceeds ~40 lines or three nesting levels, extract a helper.
- Name things for what they mean. `parsed_records` over `data`, `is_authenticated` over `flag`.
- Prefer returning `Result<T, E>` over panicking. Reserve `unwrap()`/`expect()` for cases where the invariant is provably upheld or in tests.
- Use `?` for error propagation. Define domain error types with `thiserror` or map errors at the boundary.
- Prefer iterators and combinators (`.map`, `.filter`, `.collect`) over manual index loops when the intent is clearer.
- Derive `Debug`, `Clone`, and other standard traits when useful. Derive `Default` when a zero/empty state is meaningful.
- Use `#[must_use]` on functions whose return value should not be silently ignored.
- Prefer borrowing over cloning. Clone only when ownership transfer is needed or the cost is negligible.
- Use `impl Trait` in argument position for simple generic bounds. Use explicit generics when bounds get complex or trait objects when dynamic dispatch is needed.
- Keep `unsafe` blocks minimal and document the safety invariant they rely on.
- Match the surrounding codebase's style (formatter, import order, naming) over your own preferences.

When refactoring, change behavior in the smallest diff that works. Avoid drive-by reformatting in the same change as a logic edit.
