"""Language-agnostic design review checklist loaded into the architecture reviewer agent."""

DESIGN_REVIEW = """\
## Design Review Checklist

Review all files in scope for cross-file design issues. Only report findings
where you can point to specific files and explain the concrete problem.

### paradigm_inconsistency

- Files doing the same kind of work using different styles (classes vs functions,
  async vs sync for similar operations)
- Mixed error handling strategies for the same category of operation
  (some raise, some return None, some return Result types)
- Inconsistent use of patterns — some modules use dependency injection,
  others hardcode dependencies for the same kind of work

### communication_mismatch

- Same data served or consumed via different transport mechanisms
  (HTTP polling vs WebSocket, REST vs message queue for the same domain)
- Redundant data fetching — multiple modules independently requesting
  the same data instead of sharing a single source
- Mixed serialization formats for the same data flowing between modules

### layer_violation

- Imports flowing the wrong direction (data access importing from
  presentation, utilities depending on business logic)
- Business logic embedded in transport/presentation layer code
- Direct database access from outside the data access layer
- Configuration or environment access scattered across layers
  instead of injected from the edges

### responsibility_duplication

- Multiple files implementing the same cross-cutting concern independently
  (retry logic, auth checks, caching, rate limiting, error formatting)
- Duplicated validation rules that could diverge over time
- Similar transformation logic repeated across modules instead of
  extracted to a shared utility

### dependency_coupling

- Circular imports or circular runtime dependencies between modules
- God modules that everything depends on — a change to one file
  ripples across the entire codebase
- Tight coupling between modules that should be independent —
  changes to internal details of one require changes in another
- Leaky abstractions — modules exposing implementation details
  that consumers depend on

### interface_inconsistency

- Similar operations with different signatures across modules
  (one takes positional args, another takes kwargs, another takes a config object)
- Inconsistent naming patterns for the same concept across modules
  (user_id vs userId vs uid for the same thing)
- Inconsistent return types for similar operations
  (some return raw dicts, others return typed models)
- Public interfaces that don't match the abstraction level of their module

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Per-file code quality issues (per-file reviewer owns these)
- Security vulnerabilities (per-file reviewer owns these)
- Formatting/whitespace (linter owns these)
- Type errors (type checker owns these)
- Missing tests (test runner owns these)
- README/changelog staleness (their own agents own these)"""
