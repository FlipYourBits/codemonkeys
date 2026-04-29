"""Reusable Python coding guidelines for agent prompts."""

PYTHON_GUIDELINES = """\
## Code guidelines

- Type-hint every public function and method. Prefer
  `from __future__ import annotations` so annotations
  don't evaluate at runtime.
- Keep functions short and single-purpose. If a function
  exceeds ~40 lines or three nesting levels, extract a helper.
- Name things for what they mean, not what they are.
  `parsed_records` over `data`, `is_authenticated` over `flag`.
- Prefer pure functions and explicit dependencies. Side
  effects belong at the edges of the program.
- Use dataclasses (`@dataclass(frozen=True)` when immutable)
  for structured records over ad-hoc dicts.
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

When refactoring, change behavior in the smallest diff that works.
Avoid drive-by reformatting in the same change as a logic edit."""
