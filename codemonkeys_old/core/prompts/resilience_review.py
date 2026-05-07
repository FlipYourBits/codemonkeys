"""Production resilience checklist — concurrency, error recovery, and log hygiene."""

RESILIENCE_REVIEW = """\
## Resilience Review Checklist

Review the file for production resilience issues. Only report findings at 80%+
confidence with concrete scenarios where the issue would cause a problem.

### concurrency

- Missing `await` on coroutine calls (returns a coroutine object instead of the result)
- Shared mutable state across async tasks — module-level dicts/lists mutated in coroutines
- `asyncio.gather` without `return_exceptions=True` where one failure should not kill siblings
- Synchronous blocking calls inside async functions — `time.sleep`, blocking I/O, \
`subprocess.run` without an executor
- Missing cancellation handling — `asyncio.CancelledError` caught and swallowed instead \
of propagated
- Thread-unsafe operations without locks — shared state mutated from multiple threads
- Check-then-act race conditions (TOCTOU) — file existence checks followed by open, \
key checks followed by access

### error_recovery

- I/O operations (HTTP, file, DB) without timeout configuration
- Missing retry logic on transient failures (network calls, rate-limited APIs)
- No backoff on repeated failures to the same service
- Resource leaks on error paths — connections or file handles not closed in `finally` \
or context manager
- Cascading failure risk — one downstream service failure takes out the whole request

### log_hygiene

- Error/exception paths that don't log — silent failures
- Log messages missing context — no relevant IDs, operation name, or input state
- Sensitive data in log output — passwords, tokens, PII
- Wrong log level — errors logged as `info`, debug noise at `warning`
- Bare `logger.exception()` without a descriptive message

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Broad exception catching (CODE_QUALITY owns this)
- Missing exception handling (CODE_QUALITY owns this)
- General try/except patterns (CODE_QUALITY owns this)
- PII as a security vulnerability (SECURITY_OBSERVATIONS owns this — report here \
only as an operational log hygiene concern)"""
