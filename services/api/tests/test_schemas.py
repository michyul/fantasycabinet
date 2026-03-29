"""Tests for Pydantic schemas in app.api.v1.schemas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    CabinetScopeCreate,
    DisputeCreate,
    IngestEventsRequest,
    LeagueCreate,
    LeagueUpdate,
    LineupSlotUpdate,
    LineupUpdateRequest,
    PoliticalEventIn,
    PoliticianCreate,
    PoliticianUpdate,
    ScoringRunRequest,
    SeatAssignRequest,
    StandingsRow,
    SystemConfigUpdate,
    TeamCreate,
    UserCreate,
    UserUpdate,
)

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── UserCreate ────────────────────────────────────────────────────────────────

class TestUserCreate:
    def test_valid_minimal(self):
        u = UserCreate(display_name="Alice")
        assert u.display_name == "Alice"
        assert u.roles == ["manager"]
        assert u.email is None

    def test_valid_full(self):
        u = UserCreate(
            display_name="Bob Smith",
            email="bob@example.com",
            roles=["manager", "commissioner"],
            external_subject="sub-123",
        )
        assert u.email == "bob@example.com"
        assert "commissioner" in u.roles

    def test_display_name_too_short(self):
        with pytest.raises(ValidationError):
            UserCreate(display_name="X")

    def test_display_name_too_long(self):
        with pytest.raises(ValidationError):
            UserCreate(display_name="A" * 121)

    def test_display_name_min_length_boundary(self):
        u = UserCreate(display_name="Ab")
        assert len(u.display_name) == 2

    def test_display_name_max_length_boundary(self):
        u = UserCreate(display_name="A" * 120)
        assert len(u.display_name) == 120


# ── UserUpdate ────────────────────────────────────────────────────────────────

class TestUserUpdate:
    def test_all_none(self):
        u = UserUpdate()
        assert u.display_name is None
        assert u.email is None
        assert u.roles is None

    def test_partial_update(self):
        u = UserUpdate(display_name="New Name")
        assert u.display_name == "New Name"

    def test_display_name_too_short(self):
        with pytest.raises(ValidationError):
            UserUpdate(display_name="X")


# ── LeagueCreate / CabinetScopeCreate ────────────────────────────────────────

class TestLeagueCreate:
    def test_default_format(self):
        lg = LeagueCreate(name="Hockey Night")
        assert lg.format == "season"

    def test_valid_formats(self):
        for fmt in ("season", "ladder", "tournament"):
            lg = LeagueCreate(name="Test League", format=fmt)
            assert lg.format == fmt

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            LeagueCreate(name="Bad", format="round_robin")

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            LeagueCreate(name="AB")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            LeagueCreate(name="X" * 101)

    def test_alias_is_league_create(self):
        cs = CabinetScopeCreate(name="My Scope")
        assert isinstance(cs, LeagueCreate)


# ── LeagueUpdate ──────────────────────────────────────────────────────────────

class TestLeagueUpdate:
    def test_all_none(self):
        lu = LeagueUpdate()
        assert lu.name is None
        assert lu.format is None

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            LeagueUpdate(format="invalid")

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            LeagueUpdate(name="AB")


# ── TeamCreate ────────────────────────────────────────────────────────────────

class TestTeamCreate:
    def test_valid(self):
        t = TeamCreate(name="Team Alpha")
        assert t.name == "Team Alpha"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            TeamCreate(name="X")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            TeamCreate(name="Y" * 81)


# ── LineupUpdateRequest ───────────────────────────────────────────────────────

class TestLineupUpdateRequest:
    def test_valid_mixed(self):
        req = LineupUpdateRequest(slots=[
            LineupSlotUpdate(roster_slot_id=1, lineup_status="active"),
            LineupSlotUpdate(roster_slot_id=2, lineup_status="bench"),
        ])
        assert len(req.slots) == 2
        assert req.slots[0].lineup_status == "active"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            LineupSlotUpdate(roster_slot_id=1, lineup_status="reserve")


# ── PoliticalEventIn ──────────────────────────────────────────────────────────

class TestPoliticalEventIn:
    def test_valid_minimal(self):
        ev = PoliticalEventIn(
            source_name="CBC",
            source_event_id="cbc-001",
            title="Budget passed",
            occurred_at=_NOW,
        )
        assert ev.jurisdiction == "federal"
        assert ev.event_type == "general"
        assert ev.payload == {}

    def test_with_payload(self):
        ev = PoliticalEventIn(
            source_name="Globe",
            source_event_id="g-002",
            title="Election called",
            occurred_at=_NOW,
            jurisdiction="ON",
            event_type="election",
            payload={"riding": "Spadina"},
        )
        assert ev.payload["riding"] == "Spadina"


# ── IngestEventsRequest ───────────────────────────────────────────────────────

class TestIngestEventsRequest:
    def test_empty_list(self):
        req = IngestEventsRequest(events=[])
        assert req.events == []

    def test_multiple_events(self):
        e = PoliticalEventIn(
            source_name="S",
            source_event_id="s-1",
            title="T",
            occurred_at=_NOW,
        )
        req = IngestEventsRequest(events=[e, e])
        assert len(req.events) == 2


# ── PoliticianCreate ──────────────────────────────────────────────────────────

class TestPoliticianCreate:
    def test_defaults(self):
        p = PoliticianCreate(full_name="Jane Doe")
        assert p.party == "independent"
        assert p.jurisdiction == "federal"
        assert p.asset_type == "parliamentary"
        assert p.status == "active"
        assert p.aliases == []

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            PoliticianCreate(full_name="X")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            PoliticianCreate(full_name="X" * 201)

    def test_custom_fields(self):
        p = PoliticianCreate(
            full_name="Pierre Trudeau",
            current_role="Prime Minister",
            role_tier=1,
            party="liberal",
            jurisdiction="federal",
            asset_type="executive",
            status="active",
            aliases=["PT", "P. Trudeau"],
        )
        assert p.role_tier == 1
        assert len(p.aliases) == 2


# ── PoliticianUpdate ──────────────────────────────────────────────────────────

class TestPoliticianUpdate:
    def test_all_none(self):
        pu = PoliticianUpdate()
        assert pu.current_role is None
        assert pu.role_tier is None
        assert pu.status is None
        assert pu.aliases is None


# ── DisputeCreate ─────────────────────────────────────────────────────────────

class TestDisputeCreate:
    def test_valid(self):
        d = DisputeCreate(reason="Scoring error on event X")
        assert d.target_entry_id is None

    def test_reason_too_short(self):
        with pytest.raises(ValidationError):
            DisputeCreate(reason="bad")

    def test_reason_too_long(self):
        with pytest.raises(ValidationError):
            DisputeCreate(reason="X" * 501)

    def test_with_target(self):
        d = DisputeCreate(reason="Points are incorrect", target_entry_id="ledger-abc")
        assert d.target_entry_id == "ledger-abc"


# ── ScoringRunRequest ─────────────────────────────────────────────────────────

class TestScoringRunRequest:
    def test_valid(self):
        req = ScoringRunRequest(league_id="league-123")
        assert req.league_id == "league-123"


# ── StandingsRow ──────────────────────────────────────────────────────────────

class TestStandingsRow:
    def test_valid(self):
        row = StandingsRow(
            cabinet_id="cab-1",
            cabinet_name="Team Alpha",
            total_points=120,
            rank=1,
        )
        assert row.total_points == 120

    def test_negative_points(self):
        row = StandingsRow(
            cabinet_id="cab-2",
            cabinet_name="Team Beta",
            total_points=-5,
            rank=3,
        )
        assert row.total_points == -5


# ── SystemConfigUpdate ────────────────────────────────────────────────────────

class TestSystemConfigUpdate:
    def test_string_value(self):
        sc = SystemConfigUpdate(key="ai_enabled", value="true")
        assert sc.key == "ai_enabled"

    def test_dict_value(self):
        sc = SystemConfigUpdate(key="scoring_caps", value={"max": 25})
        assert sc.value == {"max": 25}


# ── SeatAssignRequest ─────────────────────────────────────────────────────────

class TestSeatAssignRequest:
    def test_valid(self):
        r = SeatAssignRequest(mp_id="mp-abc123")
        assert r.mp_id == "mp-abc123"
