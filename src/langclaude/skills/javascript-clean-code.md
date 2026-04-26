# JavaScript clean code

When you write or modify JavaScript/TypeScript/React, follow these rules:

- Use TypeScript when the project uses it. Add explicit return types to exported functions. Prefer `interface` for object shapes, `type` for unions and intersections.
- Prefer `const` over `let`. Never use `var`.
- Use arrow functions for callbacks and short helpers. Use `function` declarations for top-level named functions that benefit from hoisting.
- Keep functions short and single-purpose. If a function exceeds ~40 lines or three nesting levels, extract a helper.
- Name things for what they mean. `fetchUserProfile` over `getData`, `isAuthenticated` over `flag`.
- Prefer immutability — spread/destructure over mutation. Use `Object.freeze` or `as const` when appropriate.
- Use `async`/`await` over raw `.then()` chains. Always handle rejections — unhandled promise rejections crash Node processes.
- Prefer `===` and `!==`. Never use `==` or `!=` except when intentionally checking `null`/`undefined` with `== null`.
- Use template literals over string concatenation.
- Use optional chaining (`?.`) and nullish coalescing (`??`) over verbose null checks.
- Prefer `Map`/`Set` over plain objects when keys are dynamic or non-string.
- In React: keep components focused. Extract hooks for reusable state logic. Prefer controlled components. Memoize (`useMemo`, `useCallback`) only when profiling shows a need — premature memoization adds complexity.
- Match the surrounding codebase's style (formatter, import order, naming) over your own preferences.

When refactoring, change behavior in the smallest diff that works. Avoid drive-by reformatting in the same change as a logic edit.
