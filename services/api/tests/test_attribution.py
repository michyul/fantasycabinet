"""Tests for app.api.v1.attribution module.

Covers:
- _name_tokens()          — token extraction helper
- _normalise()            — whitespace + lowercase normalisation
- AttributionEngine._best_match() — the matching algorithm (no DB required)
- AttributionEngine.run() — full pipeline (DB mocked)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.attribution import AttributionEngine, _name_tokens, _normalise


# ── _name_tokens ──────────────────────────────────────────────────────────────

class TestNameTokens:
    def test_simple_name(self):
        assert _name_tokens("Justin Trudeau") == ["justin", "trudeau"]

    def test_filters_short_tokens(self):
        # Single chars and 2-char tokens are removed
        tokens = _name_tokens("J. P. Mackenzie")
        assert "j" not in tokens
        assert "p" not in tokens

    def test_filters_particles(self):
        tokens = _name_tokens("Jean de la Fontaine")
        assert "de" not in tokens
        assert "la" not in tokens
        assert "jean" in tokens
        assert "fontaine" in tokens

    def test_hyphenated_name(self):
        tokens = _name_tokens("Marie-Claire Blais")
        assert "marie" in tokens
        assert "claire" in tokens
        assert "blais" in tokens

    def test_apostrophe_split(self):
        tokens = _name_tokens("O'Brien")
        assert "brien" in tokens

    def test_empty_string(self):
        assert _name_tokens("") == []

    def test_all_particles(self):
        # Every token is a particle → empty result
        assert _name_tokens("de la du") == []

    def test_van_particle(self):
        tokens = _name_tokens("Anne van Bergen")
        assert "van" not in tokens
        assert "anne" in tokens
        assert "bergen" in tokens


# ── _normalise ────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_lowercase(self):
        assert _normalise("HELLO WORLD") == "hello world"

    def test_collapse_whitespace(self):
        assert _normalise("  foo   bar  ") == "foo bar"

    def test_strip_leading_trailing(self):
        assert _normalise("  test  ") == "test"

    def test_empty(self):
        assert _normalise("") == ""

    def test_mixed_case_and_spaces(self):
        result = _normalise("  Justin   TRUDEAU  ")
        assert result == "justin trudeau"


# ── AttributionEngine._best_match ────────────────────────────────────────────

def _make_engine(confidence_floor: float = 0.65) -> AttributionEngine:
    """Build an AttributionEngine with a mocked session and disabled AI."""
    session = MagicMock()
    ai = MagicMock()
    ai.enabled = False
    return AttributionEngine(session=session, ai_client=ai, confidence_floor=confidence_floor)


def _make_politician(full_name: str, aliases: list[str] | None = None, role: str = "") -> MagicMock:
    p = MagicMock()
    p.full_name = full_name
    p.aliases_json = aliases or []
    p.current_role = role
    return p


def _make_tokens(politician) -> dict:
    from app.api.v1.attribution import _name_tokens, _normalise
    return {
        "name_tokens": _name_tokens(politician.full_name),
        "alias_phrases": [_normalise(a) for a in (politician.aliases_json or [])],
        "role_tokens": _name_tokens(politician.current_role),
    }


class TestBestMatch:
    def setup_method(self):
        self.engine = _make_engine()

    def test_direct_name_match(self):
        politician = _make_politician("Mark Carney")
        tokens = _make_tokens(politician)
        event_text = "mark carney announced new budget measures today"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is not None
        attr_type, confidence, matched = result
        assert attr_type == "direct_name"
        assert confidence >= 0.75

    def test_alias_match(self):
        politician = _make_politician("Chrystia Freeland", aliases=["the finance minister"])
        tokens = _make_tokens(politician)
        event_text = "the finance minister unveiled a new fiscal plan"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is not None
        attr_type, confidence, _ = result
        assert attr_type == "alias"
        assert confidence == pytest.approx(0.90)

    def test_role_match_below_name_confidence(self):
        politician = _make_politician("Jane Smith", role="prime minister")
        tokens = _make_tokens(politician)
        # no name tokens in text, but role tokens appear
        event_text = "the prime minister addressed parliament this morning"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is not None
        attr_type, _, _ = result
        assert attr_type == "role_title"

    def test_no_match_below_threshold(self):
        politician = _make_politician("Zebulon Quartz")
        tokens = _make_tokens(politician)
        event_text = "the budget was presented to parliament"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is None

    def test_partial_name_below_coverage(self):
        # Only one of two significant tokens present → coverage < 0.8
        politician = _make_politician("John Smith")
        tokens = _make_tokens(politician)
        event_text = "john announced changes"  # only "john", missing "smith"
        result = self.engine._best_match(event_text, politician, tokens)
        # coverage = 0.5 < 0.8 so direct_name doesn't fire; no alias/role either
        assert result is None

    def test_full_coverage_direct_name(self):
        politician = _make_politician("Jane Doe")
        tokens = _make_tokens(politician)
        event_text = "jane doe won the vote"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is not None
        assert result[0] == "direct_name"

    def test_alias_preferred_over_role(self):
        politician = _make_politician(
            "Anne Brown",
            aliases=["deputy minister"],
            role="deputy minister of finance",
        )
        tokens = _make_tokens(politician)
        event_text = "the deputy minister delivered the report"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is not None
        # alias phrase is exact; should return alias
        assert result[0] == "alias"

    def test_empty_name_tokens(self):
        politician = _make_politician("de la")  # all particles → no tokens
        tokens = _make_tokens(politician)
        event_text = "de la announced something important today"
        result = self.engine._best_match(event_text, politician, tokens)
        assert result is None


# ── AttributionEngine.run ─────────────────────────────────────────────────────

class TestAttributionEngineRun:
    def _build_engine(self, confidence_floor=0.65):
        session = MagicMock()
        ai = MagicMock()
        ai.enabled = False
        return AttributionEngine(session=session, ai_client=ai,
                                 confidence_floor=confidence_floor), session

    def test_empty_event_ids(self):
        engine, _ = self._build_engine()
        assert engine.run([]) == 0

    def test_no_events_returned(self):
        engine, session = self._build_engine()
        # scalars returns empty iterable for events query
        session.scalars.return_value = iter([])
        assert engine.run(["ev-001"]) == 0

    def test_no_politicians(self):
        engine, session = self._build_engine()
        # First scalars call → events, second → politicians
        event = MagicMock()
        event.id = "ev-001"
        event.title = "Justin Trudeau speaks"
        event.payload_json = {"summary": ""}
        session.scalars.side_effect = [iter([event]), iter([]), iter([])]
        assert engine.run(["ev-001"]) == 0

    def test_skips_existing_attributions(self):
        """run() should not create duplicate attributions."""
        engine, session = self._build_engine()

        event = MagicMock()
        event.id = "ev-001"
        event.title = "Justin Trudeau announces budget"
        event.payload_json = {"summary": "Trudeau unveiled the fiscal plan"}

        politician = MagicMock()
        politician.id = "pol-001"
        politician.full_name = "Justin Trudeau"
        politician.aliases_json = []
        politician.current_role = "Prime Minister"
        politician.status = "active"

        existing_attr = MagicMock()
        existing_attr.event_id = "ev-001"
        existing_attr.politician_id = "pol-001"

        session.scalars.side_effect = [
            iter([event]),       # events
            iter([politician]),  # politicians
            iter([existing_attr]),  # existing attributions
        ]

        written = engine.run(["ev-001"])
        assert written == 0  # pair already exists → skipped

    def test_writes_attribution_on_match(self):
        engine, session = self._build_engine()

        event = MagicMock()
        event.id = "ev-002"
        event.title = "mark carney speaks on inflation"
        event.payload_json = {"summary": "mark carney addressed reporters"}

        politician = MagicMock()
        politician.id = "pol-002"
        politician.full_name = "Mark Carney"
        politician.aliases_json = []
        politician.current_role = "Governor"
        politician.status = "active"

        session.scalars.side_effect = [
            iter([event]),
            iter([politician]),
            iter([]),   # no existing attributions
        ]

        written = engine.run(["ev-002"])
        assert written == 1
        session.add.assert_called_once()

    def test_ai_augmentation_raises_confidence(self):
        engine, session = self._build_engine(confidence_floor=0.65)
        engine.ai_client.enabled = True
        engine.ai_client.score_attribution_confidence.return_value = 0.95

        event = MagicMock()
        event.id = "ev-003"
        event.title = "mark carney addresses parliament"
        event.payload_json = {"summary": ""}

        politician = MagicMock()
        politician.id = "pol-003"
        politician.full_name = "Mark Carney"
        politician.aliases_json = []
        politician.current_role = ""
        politician.status = "active"

        session.scalars.side_effect = [
            iter([event]),
            iter([politician]),
            iter([]),
        ]

        written = engine.run(["ev-003"])
        assert written == 1
