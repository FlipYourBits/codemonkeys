"""Default model IDs for the preset nodes.

Centralised here so a future deprecation only needs one edit.

These are Anthropic-API IDs. On Bedrock or Vertex AI, pass the full
inference-profile ID (or Vertex model ID) directly to the node — see the
README's Bedrock section. `model=` accepts any string and forwards it
straight to the SDK.
"""

from __future__ import annotations

OPUS_4_7 = "claude-opus-4-7"
OPUS_4_6 = "claude-opus-4-6"
SONNET_4_6 = "claude-sonnet-4-6"
HAIKU_4_5 = "claude-haiku-4-5-20251001"

DEFAULT = OPUS_4_6
