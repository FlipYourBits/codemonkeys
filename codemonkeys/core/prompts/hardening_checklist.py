"""Post-feature architecture review addition — hardening and integration checks."""

HARDENING_CHECKLIST = """\
## Additional Focus: Hardening & Integration

Beyond the standard design review, also evaluate:

### error_paths

What happens when inputs are invalid, services are down, or operations fail?
Are errors handled at the right layer? Look for bare except blocks that swallow
context, error handlers that silently continue when they should abort, and
missing error handling on I/O boundaries.

### edge_cases

Empty collections, None values, concurrent access, boundary values — are these
handled or will they surface as bugs? Check for assumptions like "this list is
never empty" or "this key always exists" without guards.

### integration_seams

Does this feature interact correctly with existing logging, config, error
handling, and shutdown patterns? New code that ignores established patterns
(e.g., its own logger instead of the project logger, manual config reads
instead of the config system) creates maintenance burden.

### defensive_boundaries

At system edges (user input, file I/O, network, subprocess), is input validated
before being trusted internally? Internal code can trust other internal code,
but data crossing a trust boundary must be checked."""
