"""Default model IDs for the preset nodes.

Centralised here so a future deprecation only needs one edit.

NOTE: Claude Opus 4.6 is scheduled for full deprecation on 2026-06-15.
After that date, swap DEFAULT_HEAVY to OPUS_4_7 (or whichever Opus is
current) and re-run the test suite.
"""

from __future__ import annotations

OPUS_4_7 = "claude-opus-4-7"
OPUS_4_6 = "claude-opus-4-6"
SONNET_4_6 = "claude-sonnet-4-6"
HAIKU_4_5 = "claude-haiku-4-5-20251001"

DEFAULT_HEAVY = OPUS_4_6   # feature_implementer, bug_fixer
DEFAULT_LIGHT = HAIKU_4_5  # branch_namer and other one-shot text tasks
