"""Model ID constants with auto-detection for Anthropic, Bedrock, and Vertex AI.

The module exposes Anthropic direct-API IDs as the default constants.
Call ``resolve_model(anthropic_id)`` to get the correct ID for the
detected provider, or pass ``provider=`` explicitly.

Provider detection checks the same env vars the Claude Agent SDK uses:
  - ``CLAUDE_CODE_USE_BEDROCK=1`` -> Bedrock
  - ``CLAUDE_CODE_USE_VERTEX=1``  -> Vertex AI
  - Otherwise -> Anthropic direct API

Set ``AGENTPIPE_PROVIDER`` to ``anthropic``, ``bedrock``, or ``vertex``
to override auto-detection.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Anthropic direct-API IDs (canonical)
# ---------------------------------------------------------------------------
OPUS_4_7 = "claude-opus-4-7"
OPUS_4_6 = "claude-opus-4-6"
SONNET_4_6 = "claude-sonnet-4-6"
HAIKU_4_5 = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Provider-specific mappings
# ---------------------------------------------------------------------------
_BEDROCK: dict[str, str] = {
    "claude-opus-4-7": "anthropic.claude-opus-4-7",
    "claude-opus-4-6": "anthropic.claude-opus-4-6-v1",
    "claude-sonnet-4-6": "anthropic.claude-sonnet-4-6",
    "claude-haiku-4-5-20251001": "anthropic.claude-haiku-4-5-20251001-v1:0",
}

_VERTEX: dict[str, str] = {
    "claude-opus-4-7": "claude-opus-4-7",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5@20251001",
}

_PROVIDER_MAPS: dict[str, dict[str, str]] = {
    "bedrock": _BEDROCK,
    "vertex": _VERTEX,
}


def detect_provider() -> str:
    """Return ``'anthropic'``, ``'bedrock'``, or ``'vertex'``.

    Checks ``AGENTPIPE_PROVIDER`` first, then falls back to
    environment-variable heuristics.
    """
    override = os.environ.get("AGENTPIPE_PROVIDER", "").strip().lower()
    if override in ("anthropic", "bedrock", "vertex"):
        return override

    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        return "bedrock"

    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        return "vertex"

    return "anthropic"


def resolve_model(anthropic_id: str, *, provider: str | None = None) -> str:
    """Map an Anthropic model ID to the correct provider-specific ID.

    If the ID is not in the mapping (e.g. already a Bedrock ARN or an
    unknown model), it is returned unchanged.
    """
    prov = provider or detect_provider()
    mapping = _PROVIDER_MAPS.get(prov)
    if mapping is None:
        return anthropic_id
    return mapping.get(anthropic_id, anthropic_id)
