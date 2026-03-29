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
    attribution_id: str | None = None
    politician_id: str | None = None
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
    inserted_ids: list[str] = Field(default_factory=list)


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
    """Canonical politician representation. MPOut kept as alias for backward compat."""
    id: str
    name: str              # display name (= full_name for DB politicians)
    full_name: str
    current_role: str = ""
    role_tier: int = 5
    jurisdiction: str
    asset_type: str
    party: str
    status: str = "active"   # active|pending|ineligible|retired
    aliases: list[str] = Field(default_factory=list)
    source: str = "bootstrap"
    last_verified_at: datetime | None = None


# Full schema used for /politicians endpoints
PoliticianOut = MPOut


class PoliticianCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    current_role: str = ""
    role_tier: int = 5
    party: str = "independent"
    jurisdiction: str = "federal"
    asset_type: str = "parliamentary"  # executive|cabinet|opposition|parliamentary
    status: str = "active"            # active|pending|ineligible|retired
    aliases: list[str] = Field(default_factory=list)
    source: str = "admin"


class PoliticianUpdate(BaseModel):
    current_role: str | None = None
    role_tier: int | None = None
    status: str | None = None
    aliases: list[str] | None = None


class RoleHistoryOut(BaseModel):
    id: str
    politician_id: str
    previous_role: str
    new_role: str
    previous_tier: int
    new_tier: int
    changed_at: datetime
    changed_by_user_id: str


class DataSourceOut(BaseModel):
    id: str
    name: str
    source_type: str
    bootstrap: bool
    url_template: str
    config: dict
    active: bool
    politician_id: str | None = None
    created_at: datetime


class AttributionRunOut(BaseModel):
    event_ids_processed: int
    attributions_written: int


class NewsStoryOut(BaseModel):
    """Canonical news story — the unit of scoring above raw articles."""
    id: str
    canonical_title: str
    canonical_summary: str
    event_type: str
    jurisdiction: str
    significance: float          # 1–10
    sentiment: float             # −1 to +1
    is_followup: bool
    article_count: int
    status: str                  # active|settling|archived
    scored: bool
    scored_week: int | None = None
    last_scored_significance: float | None = None
    score_version: int
    rescore_count: int
    rescore_pending: bool
    first_seen_at: datetime
    last_updated_at: datetime


class StoryClusteringRunOut(BaseModel):
    stories_created: int
    stories_updated: int
    articles_assigned: int
    rescore_triggers: int


class SystemConfigOut(BaseModel):
    config: dict


class SystemConfigUpdate(BaseModel):
    key: str
    value: object


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


class BenchSignalOut(BaseModel):
    politician_id: str
    politician_name: str
    article_count: int
    top_significance: float
    top_story_title: str | None = None
    top_story_id: str | None = None


class DailyDigestTopStory(BaseModel):
    id: str
    canonical_title: str
    significance: float
    event_type: str
    jurisdiction: str
    article_count: int


class DailyDigestMPActivity(BaseModel):
    politician_id: str
    politician_name: str
    article_count: int


class DailyDigestBenchAlert(BaseModel):
    politician_id: str
    politician_name: str
    article_count: int
    in_news: bool


class DailyDigestOut(BaseModel):
    top_stories: list[DailyDigestTopStory]
    active_mps_in_news: list[DailyDigestMPActivity]
    bench_alerts: list[DailyDigestBenchAlert]
    total_articles_today: int


class WeekThemeOut(BaseModel):
    week: int
    label: str
    description: str
    multipliers: dict = Field(default_factory=dict)
    asset_multipliers: dict = Field(default_factory=dict)
    event_type_whitelist: list[str] | None = None


# ── Canonical domain-language aliases (domain-language-contract.md) ───────────────
# These names are used in all new API routes and UI.
CabinetScopeCreate = LeagueCreate
CabinetScopeUpdate = LeagueUpdate
CabinetScopeOut = LeagueOut
CabinetCreate = TeamCreate
CabinetOut = TeamOut
MandateUpdateRequest = LineupUpdateRequest
MandateUpdateOut = LineupUpdateOut
