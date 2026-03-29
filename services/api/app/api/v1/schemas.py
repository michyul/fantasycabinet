from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


LeagueFormat = Literal["season", "ladder", "tournament"]


class UserProfile(BaseModel):
    id: str
    display_name: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    issuer: str | None = None


class UserCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    email: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["manager"])
    external_subject: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = None
    roles: list[str] | None = None


class LeagueCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    format: LeagueFormat = "season"


class LeagueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    format: LeagueFormat | None = None


class LeagueOut(BaseModel):
    id: str
    name: str
    format: LeagueFormat
    commissioner_user_id: str
    current_week: int
    created_at: datetime


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class TeamOut(BaseModel):
    id: str
    scope_id: str
    manager_user_id: str
    name: str
    created_at: datetime


class RosterSlotOut(BaseModel):
    roster_slot_id: int
    slot: str
    slot_label: str
    asset_id: str
    asset_name: str
    jurisdiction: str
    asset_type: str
    party: str
    lineup_status: Literal["active", "bench"]


class RosterOut(BaseModel):
    cabinet_id: str
    items: list[RosterSlotOut]


# Canonical aliases (domain language contract)
PortfolioSeatOut = RosterSlotOut
CabinetPortfolioOut = RosterOut


class LineupSlotUpdate(BaseModel):
    roster_slot_id: int
    lineup_status: Literal["active", "bench"]


class LineupUpdateRequest(BaseModel):
    slots: list[LineupSlotUpdate]


class LineupUpdateOut(BaseModel):
    cabinet_id: str
    active_count: int
    bench_count: int


class LedgerEntryOut(BaseModel):
    id: str
    week: int
    team_id: str
    event: str
    points: int
    created_at: datetime


class StandingsRow(BaseModel):
    cabinet_id: str
    cabinet_name: str
    total_points: int
    rank: int


class StandingsOut(BaseModel):
    scope_id: str
    week: int
    items: list[StandingsRow]


class ScoringRunRequest(BaseModel):
    league_id: str


class ScoringRunOut(BaseModel):
    league_id: str
    week_scored: int
    entries_created: int


class PoliticalEventIn(BaseModel):
    source_name: str
    source_event_id: str
    title: str
    url: str | None = None
    occurred_at: datetime
    jurisdiction: str = "federal"
    event_type: str = "general"
    payload: dict = Field(default_factory=dict)


class IngestEventsRequest(BaseModel):
    events: list[PoliticalEventIn]


class IngestEventsOut(BaseModel):
    received: int
    inserted: int
    duplicates: int


class PoliticalEventOut(BaseModel):
    id: str
    source_name: str
    source_event_id: str
    title: str
    url: str | None = None
    occurred_at: datetime
    jurisdiction: str
    event_type: str
    payload: dict
    scored: bool
    scored_week: int | None = None
    created_at: datetime


class DisputeCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    target_entry_id: str | None = None


class DisputeOut(BaseModel):
    id: str
    league_id: str
    created_by_user_id: str
    reason: str
    target_entry_id: str | None = None
    status: Literal["open", "resolved"]
    created_at: datetime


class AuditLogOut(BaseModel):
    id: str
    league_id: str
    actor_user_id: str
    action: str
    metadata: dict
    created_at: datetime


class MPOut(BaseModel):
    id: str
    name: str
    jurisdiction: str
    asset_type: str
    party: str


class SeatAssignRequest(BaseModel):
    mp_id: str


class PolicyObjectiveOut(BaseModel):
    id: str
    name: str
    description: str
    event_types: list[str]
    bonus: int


class PolicySelectionRequest(BaseModel):
    objective_ids: list[str]


class PolicySelectionsOut(BaseModel):
    cabinet_id: str
    items: list[str]  # objective IDs


# ── Canonical domain-language aliases (domain-language-contract.md) ───────────────
# These names are used in all new API routes and UI.
CabinetScopeCreate = LeagueCreate
CabinetScopeUpdate = LeagueUpdate
CabinetScopeOut = LeagueOut
CabinetCreate = TeamCreate
CabinetOut = TeamOut
MandateUpdateRequest = LineupUpdateRequest
MandateUpdateOut = LineupUpdateOut
