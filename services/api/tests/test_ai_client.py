"""Tests for app.api.v1.ai_client module.

Covers:
- AIClient.from_config()              — factory constructor
- AIClient._extract_json()            — JSON extraction from raw text
- AIClient.score_attribution_confidence() — disabled path + parsing
- AIClient.score_event_significance() — disabled path + result parsing
- AIClient.is_available()             — disabled path
"""
from __future__ import annotations

from app.api.v1.ai_client import AIClient


class TestFromConfig:
    def test_defaults(self):
        ai = AIClient.from_config({})
        assert ai.base_url == AIClient.DEFAULT_BASE_URL
        assert ai.model == AIClient.DEFAULT_MODEL
        assert ai.enabled is False

    def test_custom_config(self):
        ai = AIClient.from_config({
            "ai_base_url": "http://localhost:9999",
            "ai_model": "llama3",
            "ai_enabled": True,
        })
        assert ai.base_url == "http://localhost:9999"
        assert ai.model == "llama3"
        assert ai.enabled is True

    def test_trailing_slash_stripped(self):
        ai = AIClient.from_config({"ai_base_url": "http://host:11434/"})
        assert not ai.base_url.endswith("/")


class TestExtractJson:
    def test_valid_json_object(self):
        result = AIClient._extract_json('{"confidence": 0.8, "reason": "match"}')
        assert result == {"confidence": 0.8, "reason": "match"}

    def test_json_embedded_in_text(self):
        result = AIClient._extract_json('Here is the result: {"confidence": 0.9} done')
        assert result is not None
        assert result["confidence"] == 0.9

    def test_no_json_returns_none(self):
        assert AIClient._extract_json("no json here") is None

    def test_malformed_json_returns_none(self):
        assert AIClient._extract_json("{bad json}") is None

    def test_empty_string_returns_none(self):
        assert AIClient._extract_json("") is None

    def test_nested_json(self):
        result = AIClient._extract_json('{"a": {"b": 1}}')
        assert result == {"a": {"b": 1}}


class TestScoreAttributionConfidenceDisabled:
    def setup_method(self):
        self.ai = AIClient(base_url="http://localhost", model="m", enabled=False)

    def test_returns_none_when_disabled(self):
        result = self.ai.score_attribution_confidence(
            event_title="Test event",
            event_summary="Summary",
            politician_name="Jane Doe",
            politician_role="PM",
        )
        assert result is None


class TestScoreEventSignificanceDisabled:
    def setup_method(self):
        self.ai = AIClient(base_url="http://localhost", model="m", enabled=False)

    def test_returns_none_when_disabled(self):
        result = self.ai.score_event_significance(
            event_title="Some event",
            event_type="policy",
            jurisdiction="federal",
        )
        assert result is None


class TestIsAvailable:
    def test_disabled_returns_false(self):
        ai = AIClient(base_url="http://localhost", model="m", enabled=False)
        assert ai.is_available() is False


class TestGenerateStructured:
    def test_disabled_returns_none(self):
        ai = AIClient(base_url="http://localhost", model="m", enabled=False)
        assert ai.generate_structured("any prompt") is None
