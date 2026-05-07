"""Test quality checklist — assertion rigor, test design, and isolation."""

TEST_QUALITY = """\
## Test Quality Review Checklist

Review the test file for quality issues. Only report findings at 80%+ confidence.

### assertion_quality

- Assert-free tests — test runs code but never asserts on the result
- Tautological assertions — `assert True`, `assert x == x`, \
`assert isinstance(obj, object)`
- Assertions only on type, never on value — `assert isinstance(result, dict)` \
without checking content
- Over-reliance on `mock.assert_called_once()` without verifying what was passed \
or what was returned
- Asserting on string representations instead of structured data

### test_design

- Test name doesn't match what's actually being tested
- Single test covering multiple unrelated behaviors — should be split
- Test duplicates implementation logic — reconstructs expected value using the \
same algorithm as the code under test
- Fixtures or setup that does real work the test should be verifying
- Tests that only exercise the happy path — no edge cases, no error inputs

### isolation

- Tests that depend on execution order — shared mutable state between test functions
- Tests that hit the network, filesystem, or external services without mocking \
(unintentional integration tests)
- Tests that modify module-level or class-level state without cleanup

## Exclusions — DO NOT REPORT

These belong to other review categories:
- Test coverage gaps (mechanical coverage tool owns this)
- Test framework conventions and naming style (style, not quality)
- Missing tests for specific functions (that's coverage, not quality)"""
