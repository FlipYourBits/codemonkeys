"""Tests for codemonkeys.models provider detection and model resolution."""

from __future__ import annotations


import pytest

from codemonkeys.models import (
    HAIKU_4_5,
    OPUS_4_6,
    OPUS_4_7,
    SONNET_4_6,
    detect_provider,
    resolve_model,
)


# -- detect_provider ---------------------------------------------------------


class TestDetectProvider:
    def test_defaults_to_anthropic(self, monkeypatch):
        for var in (
            "AGENTPIPE_PROVIDER",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
        ):
            monkeypatch.delenv(var, raising=False)
        assert detect_provider() == "anthropic"

    def test_detects_bedrock(self, monkeypatch):
        monkeypatch.delenv("AGENTPIPE_PROVIDER", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        assert detect_provider() == "bedrock"

    def test_detects_vertex(self, monkeypatch):
        monkeypatch.delenv("AGENTPIPE_PROVIDER", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        assert detect_provider() == "vertex"

    def test_aws_creds_alone_do_not_trigger_bedrock(self, monkeypatch):
        for var in (
            "AGENTPIPE_PROVIDER",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA...")
        assert detect_provider() == "anthropic"

    @pytest.mark.parametrize("override", ["anthropic", "bedrock", "vertex"])
    def test_explicit_override(self, monkeypatch, override):
        monkeypatch.setenv("AGENTPIPE_PROVIDER", override)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        assert detect_provider() == override

    def test_bedrock_takes_precedence_over_vertex(self, monkeypatch):
        monkeypatch.delenv("AGENTPIPE_PROVIDER", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        assert detect_provider() == "bedrock"


# -- resolve_model ------------------------------------------------------------


class TestResolveModel:
    def test_anthropic_returns_unchanged(self):
        assert resolve_model(OPUS_4_7, provider="anthropic") == "claude-opus-4-7"
        assert resolve_model(SONNET_4_6, provider="anthropic") == "claude-sonnet-4-6"

    def test_bedrock_mapping(self):
        assert (
            resolve_model(OPUS_4_7, provider="bedrock") == "anthropic.claude-opus-4-7"
        )
        assert (
            resolve_model(OPUS_4_6, provider="bedrock")
            == "anthropic.claude-opus-4-6-v1"
        )
        assert (
            resolve_model(SONNET_4_6, provider="bedrock")
            == "anthropic.claude-sonnet-4-6"
        )
        assert (
            resolve_model(HAIKU_4_5, provider="bedrock")
            == "anthropic.claude-haiku-4-5-20251001-v1:0"
        )

    def test_vertex_mapping(self):
        assert resolve_model(OPUS_4_7, provider="vertex") == "claude-opus-4-7"
        assert resolve_model(OPUS_4_6, provider="vertex") == "claude-opus-4-6"
        assert resolve_model(SONNET_4_6, provider="vertex") == "claude-sonnet-4-6"
        assert (
            resolve_model(HAIKU_4_5, provider="vertex") == "claude-haiku-4-5@20251001"
        )

    def test_unknown_model_passes_through(self):
        custom = "my-custom-model-id"
        assert resolve_model(custom, provider="bedrock") == custom
        assert resolve_model(custom, provider="vertex") == custom

    def test_already_bedrock_id_passes_through(self):
        bedrock_id = "anthropic.claude-opus-4-6-v1"
        assert resolve_model(bedrock_id, provider="bedrock") == bedrock_id

    def test_uses_detect_provider_when_none(self, monkeypatch):
        for v in (
            "AGENTPIPE_PROVIDER",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
        ):
            monkeypatch.delenv(v, raising=False)
        assert resolve_model(SONNET_4_6) == "claude-sonnet-4-6"

        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        assert resolve_model(SONNET_4_6) == "anthropic.claude-sonnet-4-6"
