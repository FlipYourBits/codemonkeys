---
name: code-quality
description: Language-agnostic code quality checklist — naming, design, complexity, structure
user-invocable: false
---

## Code Quality Review Checklist

Review the file for quality issues. Only report findings at 80%+ confidence. Return findings using the structured JSON format specified in your prompt.

### naming

- Variable/function names that don't describe intent (`data`, `result`, `tmp`, `x` outside comprehensions)
- Names that describe type instead of meaning (`user_dict` -> `users_by_id`)
- Boolean variables/functions missing is_/has_/can_/should_ prefix
- Abbreviations that aren't universally understood
- Names that shadow builtins (`list`, `type`, `id`, `input`)
- Misleading names — function does X but is named Y

### function_design

- Functions longer than ~40 lines — suggest extracting a helper
- Functions with more than 4 parameters — suggest a config dataclass
- Deeply nested conditionals (3+ levels) — suggest early returns
- Functions that do more than one thing — suggest splitting
- Side effects hidden in functions that look pure
- Boolean parameters that change behavior — suggest separate functions

### class_design

- God classes — more than ~10 public methods or mixed responsibilities
- Classes with only `__init__` — should be a dataclass
- Deep inheritance hierarchies (3+ levels) — suggest composition
- Mutable class attributes shared across all instances

### documentation

- Public functions/classes missing docstrings
- Docstring that doesn't match the current signature
- Docstring examples that use renamed or removed APIs
- Docstring that restates the function name without adding value

### error_handling

- Overly broad `except Exception` that swallows real errors
- Catching and discarding without logging (`except SomeError: pass`)
- Try/except block that's too wide — wraps more code than necessary

### code_structure

- Dead code — unreachable branches, unused imports/functions
- Commented-out code blocks
- Duplicated logic that has drifted between copies
- Magic numbers/strings without named constants

### complexity

The bar: a junior developer should understand any piece of code within 30 seconds.

- Abstraction layers that add indirection without value
- Premature generalization — flexibility that isn't used
- Clever-over-clear patterns (metaclasses, descriptor magic where plain code works)
- Over-engineered design patterns where if/else suffices

For each complexity finding, include a simplified alternative in the recommendation.

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Formatting/whitespace (linter owns these)
- Type errors (type checker owns these)
- Missing tests (test runner owns these)
- Security vulnerabilities (security skill owns these)
- README/changelog staleness (their own agents own these)
