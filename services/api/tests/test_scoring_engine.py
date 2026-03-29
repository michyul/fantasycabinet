"""Tests for app.api.v1.scoring_engine module.

Covers the pure-function static methods (no DB required) and some DB-backed
methods using mocked SQLAlchemy sessions.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.scoring_engine import ScoringEngine, ScoringResult


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_engine(**kwargs) -> ScoringEngine:
    session = MagicMock()
    ai = MagicMock()
    ai.enabled = False
    return ScoringEngine(session=session, ai_client=ai, **kwargs)


def _make_politician(
    jurisdiction: str = "federal",
    asset_type: str = "parliamentary",
    status: str = "active",
    pol_id: str = "pol-001",
    full_name: str = "Test Politician",
) -> MagicMock:
    p = MagicMock()
    p.id = pol_id
    p.jurisdiction = jurisdiction
    p.asset_type = asset_type
    p.status = status
    p.full_name = full_name
    return p


def _make_event(
    event_type: str = "general",
    jurisdiction: str = "federal",
    ev_id: str = "ev-001",
    title: str = "Test Event",
) -> MagicMock:
    e = MagicMock()
    e.id = ev_id
    e.event_type = event_type
    e.jurisdiction = jurisdiction
    e.title = title
    return e


def _make_story(
    event_type: str = "general",
    jurisdiction: str = "federal",
    significance: float = 5.0,
    sentiment: float = 0.0,
    is_followup: bool = False,
    story_id: str = "story-001",
) -> MagicMock:
    s = MagicMock()
    s.id = story_id
    s.event_type = event_type
    s.jurisdiction = jurisdiction
    s.significance = significance
    s.sentiment = sentiment
    s.is_followup = is_followup
    s.canonical_title = "Test Story"
    s.score_version = 1
    return s


# ── _confidence_multiplier ────────────────────────────────────────────────────

class TestConfidenceMultiplier:
    def test_direct_name_max_confidence(self):
        m = ScoringEngine._confidence_multiplier("direct_name", 0.95)
        assert m == pytest.approx(1.0, abs=0.01)

    def test_direct_name_lower_confidence(self):
        m = ScoringEngine._confidence_multiplier("direct_name", 0.70)
        assert m == pytest.approx(0.70 / 0.95, abs=0.001)

    def test_alias_type(self):
        m = ScoringEngine._confidence_multiplier("alias", 0.90)
        assert m == pytest.approx(0.95 * (0.90 / 0.95), abs=0.001)

    def test_role_title_type(self):
        m = ScoringEngine._confidence_multiplier("role_title", 0.65)
        # type_mult=0.60, confidence capped at 1.0 relative to 0.95
        assert m == pytest.approx(0.60 * min(0.65 / 0.95, 1.0), abs=0.001)

    def test_unknown_type_defaults_to_060(self):
        m = ScoringEngine._confidence_multiplier("unknown_type", 0.95)
        assert m == pytest.approx(0.60)

    def test_confidence_capped_at_1(self):
        # confidence > 0.95 should not produce multiplier > type_mult
        m = ScoringEngine._confidence_multiplier("direct_name", 1.0)
        assert m == pytest.approx(1.0, abs=0.01)


# ── _passes_jurisdiction_gate ────────────────────────────────────────────────

class TestJurisdictionGate:
    def test_general_event_always_passes(self):
        pol = _make_politician(jurisdiction="ON")
        ev = _make_event(event_type="general", jurisdiction="BC")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_intergovernmental_always_passes(self):
        pol = _make_politician(jurisdiction="QC")
        ev = _make_event(event_type="intergovernmental", jurisdiction="federal")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_leadership_change_always_passes(self):
        pol = _make_politician(jurisdiction="AB")
        ev = _make_event(event_type="leadership_change", jurisdiction="federal")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_federal_politician_matches_federal_event(self):
        pol = _make_politician(jurisdiction="federal")
        ev = _make_event(event_type="policy", jurisdiction="federal")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_federal_politician_matches_canada_event(self):
        pol = _make_politician(jurisdiction="federal")
        ev = _make_event(event_type="policy", jurisdiction="canada")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_federal_politician_rejects_provincial_event(self):
        pol = _make_politician(jurisdiction="federal")
        ev = _make_event(event_type="policy", jurisdiction="ON")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is False

    def test_provincial_politician_matches_own_province(self):
        pol = _make_politician(jurisdiction="ON")
        ev = _make_event(event_type="policy", jurisdiction="ON")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is True

    def test_provincial_politician_rejects_different_province(self):
        pol = _make_politician(jurisdiction="ON")
        ev = _make_event(event_type="policy", jurisdiction="BC")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is False

    def test_provincial_politician_rejects_federal_event(self):
        pol = _make_politician(jurisdiction="QC")
        ev = _make_event(event_type="policy", jurisdiction="federal")
        assert ScoringEngine._passes_jurisdiction_gate(pol, ev, "slot1") is False


# ── _passes_story_jurisdiction_gate ──────────────────────────────────────────

class TestStoryJurisdictionGate:
    def test_general_story_always_passes(self):
        pol = _make_politician(jurisdiction="BC")
        story = _make_story(event_type="general", jurisdiction="ON")
        assert ScoringEngine._passes_story_jurisdiction_gate(pol, story, "s") is True

    def test_same_jurisdiction_passes(self):
        pol = _make_politician(jurisdiction="AB")
        story = _make_story(event_type="policy", jurisdiction="AB")
        assert ScoringEngine._passes_story_jurisdiction_gate(pol, story, "s") is True

    def test_different_province_blocked(self):
        pol = _make_politician(jurisdiction="MB")
        story = _make_story(event_type="policy", jurisdiction="SK")
        assert ScoringEngine._passes_story_jurisdiction_gate(pol, story, "s") is False

    def test_federal_pol_federal_story_passes(self):
        pol = _make_politician(jurisdiction="federal")
        story = _make_story(event_type="policy", jurisdiction="federal")
        assert ScoringEngine._passes_story_jurisdiction_gate(pol, story, "s") is True


# ── _sentiment_factor ─────────────────────────────────────────────────────────

class TestSentimentFactor:
    def test_executive_positive_sentiment(self):
        # sentiment=1.0 → 0.875 + 0.375 = 1.25
        assert ScoringEngine._sentiment_factor(1.0, "executive") == pytest.approx(1.25)

    def test_executive_negative_sentiment(self):
        # sentiment=-1.0 → 0.875 - 0.375 = 0.50
        assert ScoringEngine._sentiment_factor(-1.0, "executive") == pytest.approx(0.50)

    def test_cabinet_same_as_executive(self):
        assert ScoringEngine._sentiment_factor(0.5, "cabinet") == pytest.approx(
            ScoringEngine._sentiment_factor(0.5, "executive")
        )

    def test_opposition_inverted(self):
        # negative news → bonus for opposition
        positive_for_gov = ScoringEngine._sentiment_factor(0.8, "opposition")
        negative_for_gov = ScoringEngine._sentiment_factor(-0.8, "opposition")
        assert negative_for_gov > positive_for_gov

    def test_parliamentary_small_range(self):
        low = ScoringEngine._sentiment_factor(-1.0, "parliamentary")
        high = ScoringEngine._sentiment_factor(1.0, "parliamentary")
        # Range is 0.80–1.00
        assert low == pytest.approx(0.80, abs=0.01)
        assert high == pytest.approx(1.00, abs=0.01)

    def test_unknown_asset_type_is_parliamentary_behaviour(self):
        # Falls through to else branch same as parliamentary
        result = ScoringEngine._sentiment_factor(0.0, "unknown_type")
        assert result == pytest.approx(0.9, abs=0.01)

    def test_sentiment_clamped_below_minus_one(self):
        assert ScoringEngine._sentiment_factor(-2.0, "executive") == pytest.approx(0.50)

    def test_sentiment_clamped_above_one(self):
        assert ScoringEngine._sentiment_factor(2.0, "executive") == pytest.approx(1.25)

    def test_neutral_sentiment_executive(self):
        # sentiment=0 → 0.875
        assert ScoringEngine._sentiment_factor(0.0, "executive") == pytest.approx(0.875)


# ── score_teams_for_events (mocked DB) ───────────────────────────────────────

class TestScoreTeamsForEvents:
    def _setup(self):
        engine = _make_engine()
        # Pre-load rule cache so no DB call is made for rules
        rule = MagicMock()
        rule.id = "rule-gen-parl"
        rule.event_type = "general"
        rule.asset_type = "parliamentary"
        rule.base_points = 10
        rule.affinity_bonus = 0
        rule.active = True
        rule.rule_version = "v1"
        engine._rules = {("general", "parliamentary"): rule}
        engine._rule_id_by_key = {("general", "parliamentary"): rule.id}
        return engine

    def test_empty_events_returns_empty(self):
        engine = self._setup()
        result = engine.score_teams_for_events(
            league_id="league-1",
            week=1,
            teams=[MagicMock()],
            events=[],
            policy_objectives_by_team={},
        )
        assert result == []

    def test_ineligible_politician_skipped(self):
        engine = self._setup()
        session = engine.session

        event = _make_event()
        attr = MagicMock()
        attr.politician_id = "pol-001"
        attr.event_id = "ev-001"
        attr.attribution_type = "direct_name"
        attr.confidence = 0.95
        attr.id = "attr-001"

        pol = _make_politician(status="ineligible")

        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "PM"
        slot.lineup_status = "active"

        team = MagicMock()
        team.id = "team-001"

        session.scalars.side_effect = [
            iter([attr]),          # attributions
            iter([pol]),           # politicians
            iter([slot]),          # roster slots for team
        ]
        session.scalar.return_value = None

        result = engine.score_teams_for_events(
            league_id="league-1",
            week=1,
            teams=[team],
            events=[event],
            policy_objectives_by_team={},
        )
        assert result == []

    def test_missing_rule_skips_slot(self):
        engine = self._setup()
        session = engine.session

        event = _make_event(event_type="ethics")
        attr = MagicMock()
        attr.politician_id = "pol-001"
        attr.event_id = "ev-001"
        attr.attribution_type = "direct_name"
        attr.confidence = 0.95
        attr.id = "attr-001"

        pol = _make_politician(asset_type="executive", status="active")

        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "PM"
        slot.lineup_status = "active"

        team = MagicMock()
        team.id = "team-001"

        session.scalars.side_effect = [
            iter([attr]),
            iter([pol]),
            iter([slot]),
        ]

        result = engine.score_teams_for_events(
            league_id="league-1",
            week=1,
            teams=[team],
            events=[event],
            policy_objectives_by_team={},
        )
        # No rule for (ethics, executive) → skipped
        assert result == []

    def test_successful_scoring(self):
        engine = self._setup()
        session = engine.session

        event = _make_event(event_type="general", jurisdiction="federal")
        attr = MagicMock()
        attr.politician_id = "pol-001"
        attr.event_id = "ev-001"
        attr.attribution_type = "direct_name"
        attr.confidence = 0.95
        attr.id = "attr-001"

        pol = _make_politician(asset_type="parliamentary", jurisdiction="federal", status="active")

        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "House"
        slot.lineup_status = "active"

        team = MagicMock()
        team.id = "team-001"

        session.scalars.side_effect = [
            iter([attr]),
            iter([pol]),
            iter([slot]),
        ]

        result = engine.score_teams_for_events(
            league_id="league-1",
            week=1,
            teams=[team],
            events=[event],
            policy_objectives_by_team={},
        )
        assert len(result) == 1
        sr = result[0]
        assert isinstance(sr, ScoringResult)
        assert sr.team_id == "team-001"
        assert sr.base_points == 10
        assert sr.final_points >= engine.min_pts
        assert sr.final_points <= engine.max_pts


# ── score_ineligibility_penalties ────────────────────────────────────────────

class TestScoreIneligibilityPenalties:
    def test_no_ineligible_politicians(self):
        engine = _make_engine()
        session = engine.session

        pol = _make_politician(status="active")
        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "PM"

        team = MagicMock()
        team.id = "team-001"

        session.scalars.return_value = iter([slot])
        session.get.return_value = pol

        result = engine.score_ineligibility_penalties("league-1", 1, [team])
        assert result == []

    def test_ineligible_politician_gets_penalty(self):
        engine = _make_engine()
        session = engine.session

        pol = _make_politician(status="ineligible")
        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "PM"

        team = MagicMock()
        team.id = "team-001"

        session.scalars.return_value = iter([slot])
        session.get.return_value = pol

        result = engine.score_ineligibility_penalties("league-1", 1, [team],
                                                       penalty_points=-3)
        assert len(result) == 1
        assert result[0].final_points == -3
        assert result[0].attribution_type == "system"

    def test_penalty_uses_configured_points(self):
        engine = _make_engine()
        session = engine.session

        pol = _make_politician(status="ineligible")
        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "House"

        team = MagicMock()
        team.id = "team-002"

        session.scalars.return_value = iter([slot])
        session.get.return_value = pol

        result = engine.score_ineligibility_penalties("league-1", 2, [team],
                                                       penalty_points=-5)
        assert result[0].final_points == -5

    def test_multiple_ineligible_slots(self):
        engine = _make_engine()
        session = engine.session

        pol = _make_politician(status="ineligible")
        slot1 = MagicMock()
        slot1.asset_id = "pol-001"
        slot1.slot = "PM"
        slot2 = MagicMock()
        slot2.asset_id = "pol-001"
        slot2.slot = "DPM"

        team = MagicMock()
        team.id = "team-003"

        session.scalars.return_value = iter([slot1, slot2])
        session.get.return_value = pol

        result = engine.score_ineligibility_penalties("league-1", 3, [team])
        assert len(result) == 2


# ── per-asset caps ────────────────────────────────────────────────────────────

class TestPerAssetCaps:
    def test_max_cap_applied(self):
        engine = _make_engine(max_points_per_asset=5)
        session = engine.session

        rule = MagicMock()
        rule.id = "rule-001"
        rule.base_points = 100
        rule.affinity_bonus = 0
        engine._rules = {("general", "parliamentary"): rule}
        engine._rule_id_by_key = {("general", "parliamentary"): "rule-001"}

        event = _make_event()
        attr = MagicMock()
        attr.politician_id = "pol-001"
        attr.event_id = "ev-001"
        attr.attribution_type = "direct_name"
        attr.confidence = 0.95
        attr.id = "attr-001"

        pol = _make_politician(asset_type="parliamentary", jurisdiction="federal")
        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "House"
        slot.lineup_status = "active"
        team = MagicMock()
        team.id = "team-001"

        session.scalars.side_effect = [iter([attr]), iter([pol]), iter([slot])]

        result = engine.score_teams_for_events(
            "league-1", 1, [team], [event], {}
        )
        assert result[0].final_points <= 5

    def test_min_cap_applied(self):
        engine = _make_engine(min_points_per_asset=-2)
        session = engine.session

        rule = MagicMock()
        rule.id = "rule-001"
        rule.base_points = -100
        rule.affinity_bonus = 0
        engine._rules = {("general", "parliamentary"): rule}
        engine._rule_id_by_key = {("general", "parliamentary"): "rule-001"}

        event = _make_event()
        attr = MagicMock()
        attr.politician_id = "pol-001"
        attr.event_id = "ev-001"
        attr.attribution_type = "direct_name"
        attr.confidence = 0.95
        attr.id = "attr-001"

        pol = _make_politician(asset_type="parliamentary", jurisdiction="federal")
        slot = MagicMock()
        slot.asset_id = "pol-001"
        slot.slot = "House"
        slot.lineup_status = "active"
        team = MagicMock()
        team.id = "team-001"

        session.scalars.side_effect = [iter([attr]), iter([pol]), iter([slot])]

        result = engine.score_teams_for_events(
            "league-1", 1, [team], [event], {}
        )
        assert result[0].final_points >= -2
