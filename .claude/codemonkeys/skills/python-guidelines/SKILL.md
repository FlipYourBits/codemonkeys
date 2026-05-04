---
name: python-guidelines
description: Python code conventions — type hints, pathlib, pydantic, function design, error handling
user-invocable: false
---

## Code guidelines

- Use `from __future__ import annotations` in every file so
  annotations don't evaluate at runtime.
- Type-hint every public function and method. Use `Literal` types
  for constrained string params (e.g., `scope: Literal["diff", "repo"]`).
- Use Pydantic `BaseModel` for structured data, not ad-hoc dicts.
  Use dataclasses (`@dataclass(frozen=True)` when immutable) for
  simple structured records that don't need validation.
- Keep functions short and single-purpose. If a function
  exceeds ~40 lines or three nesting levels, extract a helper.
- Name things for what they mean, not what they are.
  `parsed_records` over `data`, `is_authenticated` over `flag`.
- Prefer pure functions and explicit dependencies. Side
  effects belong at the edges of the program.
- Don't catch `Exception` broadly. Catch the narrowest type
  you can name and let the rest crash with a useful traceback.
- Don't write defensive code for situations that cannot occur
  given the call graph. Trust internal invariants.
- Don't add comments that restate the code. Comments explain
  *why* — a non-obvious constraint, a workaround, a subtle invariant.
- Match the surrounding codebase's style (formatter, import order,
  naming) over your own preferences.
- Use `pathlib.Path` over `os.path` string juggling.
- Use f-strings, not `.format()` or `%` formatting.
- Use `with` for any resource that has a `close()`.
- No dead code, no commented-out blocks, no `# TODO` without a
  concrete plan attached.

When refactoring, change behavior in the smallest diff that works.
Avoid drive-by reformatting in the same change as a logic edit.
