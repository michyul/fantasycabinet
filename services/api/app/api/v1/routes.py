import os

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.schemas import (
    AchievementOut,
    AuditLogOut,
    AttributionRunOut,
    BenchSignalOut,
    CabinetCreate,
    CabinetOut,
    CabinetScopeCreate,
    CabinetScopeOut,
    CabinetScopeUpdate,
    DailyDigestOut,
    DataSourceOut,
    DisputeCreate,
    DisputeOut,
    IngestEventsOut,
    IngestEventsRequest,
    LeagueCreate,
    LeagueOut,
    LeagueUpdate,
    LedgerEntryOut,
    LineupUpdateOut,
    LineupUpdateRequest,
    ManagerStatsOut,
    MandateUpdateOut,
    MandateUpdateRequest,
    MPOut,
    NewsStoryOut,
    PolicyObjectiveOut,
    PolicySelectionRequest,
    PolicySelectionsOut,
    PoliticianOut,
    PoliticianCreate,
    PoliticianUpdate,
    PoliticalEventOut,
    RoleHistoryOut,
    RosterOut,
    RosterSlotOut,
    ScoringRunOut,
    ScoringRunRequest,
    SeatAssignRequest,
    StandingsOut,
    StandingsRow,
    StoryClusteringRunOut,
    SystemConfigOut,
    SystemConfigUpdate,
    TeamCreate,
    TeamOut,
    UserCreate,
    UserProfile,
    UserUpdate,
    WeekThemeOut,
)
from app.api.v1.persistent_store import POLICY_OBJECTIVES, PORTFOLIO_SEAT_LABELS, roles_for_user, store

router = APIRouter()


@router.get("/auth/me")
def me(
    x_auth_sub: str | None = Header(default=None),
    x_auth_name: str | None = Header(default=None),
    x_auth_email: str | None = Header(default=None),
    x_auth_roles: str | None = Header(default=None),
) -> UserProfile:
    roles = [role.strip() for role in (x_auth_roles or "manager").split(",") if role.strip()]
    user = store.upsert_user(
        external_subject=x_auth_sub or "demo-user",
        display_name=x_auth_name or "Demo Manager",
        email=x_auth_email,
        roles=roles,
        issuer=os.getenv("OIDC_ISSUER"),
    )
    return UserProfile(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        roles=roles_for_user(user),
        issuer=user.issuer,
    )


@router.get("/users")
def list_users() -> dict[str, list[UserProfile]]:
    users = store.list_users()
    return {
        "items": [
            UserProfile(
                id=user.id,
                display_name=user.display_name,
                email=user.email,
                roles=roles_for_user(user),
                issuer=user.issuer,
            )
            for user in users
        ]
    }


@router.get("/users/{user_id}")
def get_user(user_id: str) -> UserProfile:
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserProfile(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        roles=roles_for_user(user),
        issuer=user.issuer,
    )


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> UserProfile:
    user = store.create_user(
        display_name=payload.display_name,
        email=payload.email,
        roles=payload.roles,
        external_subject=payload.external_subject,
        issuer=os.getenv("OIDC_ISSUER"),
    )
    return UserProfile(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        roles=roles_for_user(user),
        issuer=user.issuer,
    )


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate) -> UserProfile:
    current = store.get_user(user_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    fields_set = payload.model_fields_set
    next_display_name = payload.display_name if "display_name" in fields_set else current.display_name
    next_email = payload.email if "email" in fields_set else current.email
    next_roles = payload.roles if "roles" in fields_set else roles_for_user(current)

    user = store.update_user(
        user_id=user_id,
        display_name=next_display_name,
        email=next_email,
        roles=next_roles,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserProfile(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        roles=roles_for_user(user),
        issuer=user.issuer,
    )


@router.get("/assets")
def list_assets() -> dict[str, list[dict]]:
    politicians = store.list_politicians(status="active")
    return {
        "items": [
            {
                "id": p.id,
                "name": p.full_name,
                "jurisdiction": p.jurisdiction,
                "assetType": p.asset_type,
                "party": p.party,
            }
            for p in politicians
        ]
    }

@router.get("/mps")
def list_mps() -> dict[str, list[MPOut]]:
    """Backward-compat alias for /politicians."""
    politicians = store.list_politicians()
    return {
        "items": [
            MPOut(
                id=p.id,
                name=p.full_name,
                full_name=p.full_name,
                current_role=p.current_role,
                role_tier=p.role_tier,
                jurisdiction=p.jurisdiction,
                asset_type=p.asset_type,
                party=p.party,
                status=p.status,
                aliases=p.aliases_json if isinstance(p.aliases_json, list) else [],
                source=p.source,
                last_verified_at=p.last_verified_at,
            )
            for p in politicians
        ]
    }

# ── Cabinet Scope routes (canonical) ────────────────────────────────────────

@router.get("/cabinet-scopes")
def list_cabinet_scopes() -> dict[str, list[CabinetScopeOut]]:
    return list_leagues()


@router.post("/cabinet-scopes", status_code=status.HTTP_201_CREATED)
def create_cabinet_scope(payload: CabinetScopeCreate, x_auth_sub: str | None = Header(default=None)) -> CabinetScopeOut:
    return create_league(payload, x_auth_sub)


@router.get("/cabinet-scopes/{scope_id}")
def get_cabinet_scope(scope_id: str) -> CabinetScopeOut:
    return get_league(scope_id)


@router.patch("/cabinet-scopes/{scope_id}")
def update_cabinet_scope(
    scope_id: str,
    payload: CabinetScopeUpdate,
    x_auth_sub: str | None = Header(default=None),
) -> CabinetScopeOut:
    league = store.get_league(scope_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cabinet scope not found")
    updated = store.update_league(scope_id, name=payload.name, format=payload.format)
    return CabinetScopeOut(
        id=updated.id,
        name=updated.name,
        format=updated.format,
        commissioner_user_id=updated.commissioner_user_id,
        current_week=updated.current_week,
        created_at=updated.created_at,
    )


@router.get("/cabinet-scopes/{scope_id}/cabinets")
def list_cabinets(scope_id: str) -> dict[str, list[CabinetOut]]:
    return list_teams(scope_id)


@router.post("/cabinet-scopes/{scope_id}/cabinets", status_code=status.HTTP_201_CREATED)
def create_cabinet(scope_id: str, payload: CabinetCreate, x_auth_sub: str | None = Header(default=None)) -> CabinetOut:
    return create_team(scope_id, payload, x_auth_sub)


@router.get("/cabinet-scopes/{scope_id}/standings")
def cabinet_scope_standings(scope_id: str) -> StandingsOut:
    return standings(scope_id)


@router.get("/cabinet-scopes/{scope_id}/audit-log")
def cabinet_scope_audit_log(scope_id: str) -> dict[str, list[AuditLogOut]]:
    return league_audit_log(scope_id)


@router.get("/cabinet-scopes/{scope_id}/week-theme")
def get_week_theme(scope_id: str) -> WeekThemeOut | None:
    """Return the current week's modifier/theme for this cabinet scope, or null if none is active."""
    league = _assert_league_exists(scope_id)
    week = league.current_week
    cfg = store.get_system_config()
    week_modifiers = cfg.get("week_modifiers")
    if not isinstance(week_modifiers, dict):
        return None
    mod = week_modifiers.get(str(week))
    if not mod:
        return None
    return WeekThemeOut(
        week=week,
        label=mod.get("label", ""),
        description=mod.get("description", ""),
        multipliers=mod.get("multipliers", {}),
        asset_multipliers=mod.get("asset_multipliers", {}),
        event_type_whitelist=mod.get("event_type_whitelist"),
    )


@router.post("/cabinet-scopes/{scope_id}/disputes", status_code=status.HTTP_201_CREATED)
def create_cabinet_scope_dispute(
    scope_id: str,
    payload: DisputeCreate,
    x_auth_sub: str | None = Header(default=None),
) -> DisputeOut:
    return create_dispute(scope_id, payload, x_auth_sub)


@router.get("/cabinets/{cabinet_id}/ledger")
def cabinet_ledger(cabinet_id: str, scope_id: str = Query(...), week: int | None = Query(default=None)) -> dict[str, list[LedgerEntryOut]]:
    return team_ledger(cabinet_id, scope_id, week)


@router.patch("/cabinets/{cabinet_id}/mandate")
def cabinet_mandate(cabinet_id: str, payload: MandateUpdateRequest) -> MandateUpdateOut:
    return update_lineup(cabinet_id, payload)


@router.patch("/cabinets/{cabinet_id}/portfolio/{slot_name}")
def assign_mp_to_seat(cabinet_id: str, slot_name: str, payload: SeatAssignRequest) -> RosterSlotOut:
    try:
        slot = store.assign_mp_to_seat(cabinet_id, slot_name, payload.mp_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    pol = store.get_politician(slot.asset_id)
    return RosterSlotOut(
        roster_slot_id=slot.id,
        slot=slot.slot,
        slot_label=PORTFOLIO_SEAT_LABELS.get(slot.slot, slot.slot),
        asset_id=slot.asset_id,
        asset_name=pol.full_name if pol else slot.asset_id,
        jurisdiction=pol.jurisdiction if pol else "unknown",
        asset_type=pol.asset_type if pol else "unknown",
        party=pol.party if pol else "unknown",
        lineup_status="active" if slot.lineup_status == "active" else "bench",
    )


@router.get("/policy-objectives")
def list_policy_objectives() -> dict[str, list[PolicyObjectiveOut]]:
    return {
        "items": [
            PolicyObjectiveOut(
                id=obj.id,
                name=obj.name,
                description=obj.description,
                event_types=obj.event_types,
                bonus=obj.bonus,
            )
            for obj in POLICY_OBJECTIVES
        ]
    }


@router.get("/cabinets/{cabinet_id}/policy-objectives")
def get_cabinet_policy_objectives(cabinet_id: str) -> PolicySelectionsOut:
    items = store.get_cabinet_policy_objectives(cabinet_id)
    return PolicySelectionsOut(cabinet_id=cabinet_id, items=items)


@router.put("/cabinets/{cabinet_id}/policy-objectives")
def set_cabinet_policy_objectives(cabinet_id: str, payload: PolicySelectionRequest) -> PolicySelectionsOut:
    saved = store.set_cabinet_policy_objectives(cabinet_id, payload.objective_ids)
    return PolicySelectionsOut(cabinet_id=cabinet_id, items=saved)


@router.get("/cabinets/{cabinet_id}/bench-signals")
def get_bench_signals(cabinet_id: str) -> dict[str, list[BenchSignalOut]]:
    """Return daily attribution activity for each bench (monitoring) politician."""
    signals = store.compute_bench_signals(cabinet_id)
    return {"items": [BenchSignalOut(**s) for s in signals]}


@router.get("/cabinets/{cabinet_id}/daily-digest")
def get_daily_digest(cabinet_id: str) -> DailyDigestOut:
    """Return today's top stories, active MP activity, and bench alerts in one call."""
    digest = store.daily_digest(cabinet_id)
    return DailyDigestOut(**digest)


@router.get("/cabinets/{cabinet_id}/achievements")
def get_cabinet_achievements(cabinet_id: str) -> dict[str, list[AchievementOut]]:
    """Return all achievements earned by this cabinet."""
    ach_defs = {d["id"]: d for d in store.ACHIEVEMENT_DEFS}
    achievements = store.get_cabinet_achievements(cabinet_id)
    return {
        "items": [
            AchievementOut(
                id=a.id,
                team_id=a.team_id,
                achievement_id=a.achievement_id,
                name=ach_defs.get(a.achievement_id, {}).get("name", a.achievement_id),
                description=ach_defs.get(a.achievement_id, {}).get("description", ""),
                earned_at=a.earned_at,
                week=a.week,
                metadata=a.metadata_json or {},
            )
            for a in achievements
        ]
    }


@router.get("/cabinets/{cabinet_id}/stats")
def get_cabinet_stats(cabinet_id: str) -> ManagerStatsOut:
    """Return streak stats for this cabinet."""
    stats = store.get_cabinet_stats(cabinet_id)
    if stats is None:
        return ManagerStatsOut(team_id=cabinet_id)
    return ManagerStatsOut(
        team_id=stats.team_id,
        participation_streak=stats.participation_streak,
        positive_streak=stats.positive_streak,
        longest_participation_streak=stats.longest_participation_streak,
        longest_positive_streak=stats.longest_positive_streak,
        updated_at=stats.updated_at,
    )


@router.post("/internal/events/ingest")
def ingest_events(payload: IngestEventsRequest) -> IngestEventsOut:
    received, inserted, duplicates, inserted_ids = store.ingest_events(payload.events)
    return IngestEventsOut(received=received, inserted=inserted, duplicates=duplicates, inserted_ids=inserted_ids)


@router.get("/events")
def list_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, list[PoliticalEventOut]]:
    events = store.list_events(limit=limit)
    return {
        "items": [
            PoliticalEventOut(
                id=event.id,
                source_name=event.source_name,
                source_event_id=event.source_event_id,
                title=event.title,
                url=event.url,
                occurred_at=event.occurred_at,
                jurisdiction=event.jurisdiction,
                event_type=event.event_type,
                payload=event.payload_json,
                scored=event.scored,
                scored_week=event.scored_week,
                created_at=event.created_at,
            )
            for event in events
        ]
    }


@router.get("/leagues")
def list_leagues() -> dict[str, list[LeagueOut]]:
    leagues = store.list_leagues()
    return {
        "items": [
            LeagueOut(
                id=league.id,
                name=league.name,
                format=league.format,
                commissioner_user_id=league.commissioner_user_id,
                current_week=league.current_week,
                created_at=league.created_at,
            )
            for league in leagues
        ]
    }


@router.post("/leagues", status_code=status.HTTP_201_CREATED)
def create_league(payload: LeagueCreate, x_auth_sub: str | None = Header(default=None)) -> LeagueOut:
    actor = store.upsert_user(
        external_subject=x_auth_sub or "demo-user",
        display_name="Scope Commissioner",
        email=None,
        roles=["manager", "commissioner"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    league = store.create_league(payload, commissioner_user_id=actor.id)
    return LeagueOut(
        id=league.id,
        name=league.name,
        format=league.format,
        commissioner_user_id=league.commissioner_user_id,
        current_week=league.current_week,
        created_at=league.created_at,
    )


@router.get("/leagues/{league_id}")
def get_league(league_id: str) -> LeagueOut:
    league = store.get_league(league_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return LeagueOut(
        id=league.id,
        name=league.name,
        format=league.format,
        commissioner_user_id=league.commissioner_user_id,
        current_week=league.current_week,
        created_at=league.created_at,
    )


@router.get("/leagues/{league_id}/teams")
def list_teams(league_id: str) -> dict[str, list[TeamOut]]:
    _assert_league_exists(league_id)
    teams = store.list_teams(league_id)
    return {
        "items": [
            TeamOut(
                id=team.id,
                scope_id=team.league_id,
                manager_user_id=team.manager_user_id,
                name=team.name,
                created_at=team.created_at,
            )
            for team in teams
        ]
    }


@router.post("/leagues/{league_id}/teams", status_code=status.HTTP_201_CREATED)
def create_team(league_id: str, payload: TeamCreate, x_auth_sub: str | None = Header(default=None)) -> TeamOut:
    _assert_league_exists(league_id)
    actor = store.upsert_user(
        external_subject=x_auth_sub or "demo-user",
        display_name="Team Manager",
        email=None,
        roles=["manager"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    team = store.create_team(league_id, manager_user_id=actor.id, payload=payload)
    return TeamOut(
        id=team.id,
        scope_id=team.league_id,
        manager_user_id=team.manager_user_id,
        name=team.name,
        created_at=team.created_at,
    )


@router.get("/teams/{team_id}/roster")
def roster(team_id: str) -> RosterOut:
    slots = store.roster_for_team(team_id)
    if not slots:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team roster not found")
    # Build politician lookup from asset_ids on the roster
    pol_ids = [slot.asset_id for slot in slots]
    politicians = {p.id: p for p in [
        store.get_politician(pid) for pid in pol_ids
        if store.get_politician(pid) is not None
    ]}
    items = [
        RosterSlotOut(
            roster_slot_id=slot.id,
            slot=slot.slot,
            slot_label=PORTFOLIO_SEAT_LABELS.get(slot.slot, slot.slot),
            asset_id=slot.asset_id,
            asset_name=politicians[slot.asset_id].full_name if slot.asset_id in politicians else slot.asset_id,
            jurisdiction=politicians[slot.asset_id].jurisdiction if slot.asset_id in politicians else "unknown",
            asset_type=politicians[slot.asset_id].asset_type if slot.asset_id in politicians else "unknown",
            party=politicians[slot.asset_id].party if slot.asset_id in politicians else "unknown",
            lineup_status="active" if slot.lineup_status == "active" else "bench",
        )
        for slot in slots
    ]
    return RosterOut(cabinet_id=team_id, items=items)


# Canonical route alias
@router.get("/cabinets/{cabinet_id}/portfolio")
def cabinet_portfolio(cabinet_id: str) -> RosterOut:
    return roster(cabinet_id)


@router.patch("/teams/{team_id}/lineup")
@router.patch("/teams/{team_id}/mandate")
def update_lineup(team_id: str, payload: LineupUpdateRequest) -> LineupUpdateOut:
    try:
        updated = store.update_lineup(
            team_id=team_id,
            updates=[(slot.roster_slot_id, slot.lineup_status) for slot in payload.slots],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    active_count, bench_count = updated
    return LineupUpdateOut(cabinet_id=team_id, active_count=active_count, bench_count=bench_count)


@router.get("/teams/{team_id}/ledger")
def team_ledger(team_id: str, league_id: str = Query(...), week: int | None = Query(default=None)) -> dict[str, list[LedgerEntryOut]]:
    entries = store.ledger_for_team(league_id=league_id, team_id=team_id, week=week)
    return {
        "items": [
            LedgerEntryOut(
                id=entry.id,
                week=entry.week,
                team_id=entry.team_id,
                event=entry.event,
                points=entry.points,
                attribution_id=entry.attribution_id,
                politician_id=entry.politician_id,
                created_at=entry.created_at,
            )
            for entry in entries
        ]
    }


@router.get("/leagues/{league_id}/standings")
def standings(league_id: str) -> StandingsOut:
    league = _assert_league_exists(league_id)
    ranked = store.standings(league_id)
    items = [
        StandingsRow(
            cabinet_id=team.id,
            cabinet_name=team.name,
            total_points=total_points,
            rank=index + 1,
            participation_streak=stats.participation_streak if stats else 0,
            positive_streak=stats.positive_streak if stats else 0,
        )
        for index, (team, total_points, stats) in enumerate(ranked)
    ]
    return StandingsOut(scope_id=league_id, week=league.current_week - 1, items=items)


@router.post("/internal/scoring/run")
def run_scoring(payload: ScoringRunRequest) -> ScoringRunOut:
    _assert_league_exists(payload.league_id)
    week_scored, entries_created = store.score_league_week(payload.league_id)
    return ScoringRunOut(league_id=payload.league_id, week_scored=week_scored, entries_created=entries_created)


@router.post("/leagues/{league_id}/disputes", status_code=status.HTTP_201_CREATED)
def create_dispute(
    league_id: str,
    payload: DisputeCreate,
    x_auth_sub: str | None = Header(default=None),
) -> DisputeOut:
    _assert_league_exists(league_id)
    actor = store.upsert_user(
        external_subject=x_auth_sub or "demo-user",
        display_name="Dispute Manager",
        email=None,
        roles=["manager"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    dispute = store.create_dispute(
        league_id=league_id,
        created_by_user_id=actor.id,
        reason=payload.reason,
        target_entry_id=payload.target_entry_id,
    )
    return DisputeOut(
        id=dispute.id,
        league_id=dispute.league_id,
        created_by_user_id=dispute.created_by_user_id,
        reason=dispute.reason,
        target_entry_id=dispute.target_entry_id,
        status=dispute.status,
        created_at=dispute.created_at,
    )


@router.post("/leagues/{league_id}/disputes/{dispute_id}/resolve")
def resolve_dispute(
    league_id: str,
    dispute_id: str,
    x_auth_sub: str | None = Header(default=None),
) -> DisputeOut:
    _assert_league_exists(league_id)
    actor = store.upsert_user(
        external_subject=x_auth_sub or "demo-user",
        display_name="Commissioner",
        email=None,
        roles=["manager", "commissioner"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    dispute = store.resolve_dispute(league_id=league_id, dispute_id=dispute_id, actor_user_id=actor.id)
    if dispute is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    return DisputeOut(
        id=dispute.id,
        league_id=dispute.league_id,
        created_by_user_id=dispute.created_by_user_id,
        reason=dispute.reason,
        target_entry_id=dispute.target_entry_id,
        status=dispute.status,
        created_at=dispute.created_at,
    )


@router.get("/leagues/{league_id}/audit-log")
def league_audit_log(league_id: str) -> dict[str, list[AuditLogOut]]:
    _assert_league_exists(league_id)
    return {
        "items": [
            AuditLogOut(
                id=item.id,
                league_id=item.league_id,
                actor_user_id=item.actor_user_id,
                action=item.action,
                metadata=item.metadata_json,
                created_at=item.created_at,
            )
            for item in store.list_audit(league_id)
        ]
    }


# ── Politician routes ─────────────────────────────────────────────────────────

@router.get("/politicians")
def list_politicians(status_filter: str | None = Query(default=None, alias="status")) -> dict[str, list[PoliticianOut]]:
    politicians = store.list_politicians(status=status_filter)
    return {
        "items": [
            PoliticianOut(
                id=p.id,
                name=p.full_name,
                full_name=p.full_name,
                current_role=p.current_role,
                role_tier=p.role_tier,
                jurisdiction=p.jurisdiction,
                asset_type=p.asset_type,
                party=p.party,
                status=p.status,
                aliases=p.aliases_json if isinstance(p.aliases_json, list) else [],
                source=p.source,
                last_verified_at=p.last_verified_at,
            )
            for p in politicians
        ]
    }


@router.get("/politicians/{politician_id}")
def get_politician(politician_id: str) -> PoliticianOut:
    p = store.get_politician(politician_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Politician not found")
    return PoliticianOut(
        id=p.id,
        name=p.full_name,
        full_name=p.full_name,
        current_role=p.current_role,
        role_tier=p.role_tier,
        jurisdiction=p.jurisdiction,
        asset_type=p.asset_type,
        party=p.party,
        status=p.status,
        aliases=p.aliases_json if isinstance(p.aliases_json, list) else [],
        source=p.source,
        last_verified_at=p.last_verified_at,
    )


@router.patch("/politicians/{politician_id}")
def update_politician(
    politician_id: str,
    payload: PoliticianUpdate,
    x_auth_roles: str | None = Header(default=None),
) -> PoliticianOut:
    roles = [r.strip() for r in (x_auth_roles or "").split(",") if r.strip()]
    if "commissioner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner role required")
    p = store.get_politician(politician_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Politician not found")
    updated = store.update_politician_role(
        politician_id=politician_id,
        new_role=payload.current_role if payload.current_role is not None else p.current_role,
        new_tier=payload.role_tier if payload.role_tier is not None else p.role_tier,
        changed_by_user_id="system",
        new_status=payload.status,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Politician not found")
    return PoliticianOut(
        id=updated.id,
        name=updated.full_name,
        full_name=updated.full_name,
        current_role=updated.current_role,
        role_tier=updated.role_tier,
        jurisdiction=updated.jurisdiction,
        asset_type=updated.asset_type,
        party=updated.party,
        status=updated.status,
        aliases=updated.aliases_json if isinstance(updated.aliases_json, list) else [],
        source=updated.source,
        last_verified_at=updated.last_verified_at,
    )


@router.get("/politicians/{politician_id}/role-history")
def get_politician_role_history(politician_id: str) -> dict[str, list[RoleHistoryOut]]:
    history = store.list_role_history(politician_id)
    return {
        "items": [
            RoleHistoryOut(
                id=h.id,
                politician_id=h.politician_id,
                previous_role=h.previous_role,
                new_role=h.new_role,
                previous_tier=h.previous_tier,
                new_tier=h.new_tier,
                changed_at=h.changed_at,
                changed_by_user_id=h.changed_by_user_id,
            )
            for h in history
        ]
    }


# ── Admin config routes ───────────────────────────────────────────────────────

@router.get("/admin/config")
def get_system_config(x_auth_roles: str | None = Header(default=None)) -> SystemConfigOut:
    roles = [r.strip() for r in (x_auth_roles or "").split(",") if r.strip()]
    if "commissioner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner role required")
    return SystemConfigOut(config=store.get_system_config())


@router.patch("/admin/config")
def update_system_config(
    payload: SystemConfigUpdate,
    x_auth_roles: str | None = Header(default=None),
    x_auth_sub: str | None = Header(default=None),
) -> SystemConfigOut:
    roles = [r.strip() for r in (x_auth_roles or "").split(",") if r.strip()]
    if "commissioner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner role required")
    store.update_system_config(key=payload.key, value=payload.value, updated_by=x_auth_sub or "system")
    return SystemConfigOut(config=store.get_system_config())


@router.post("/admin/bootstrap/run")
def run_bootstrap(x_auth_roles: str | None = Header(default=None)) -> dict:
    roles = [r.strip() for r in (x_auth_roles or "").split(",") if r.strip()]
    if "commissioner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner role required")
    from app.api.v1.bootstrap_engine import BootstrapEngine
    from sqlalchemy.orm import Session as SASession
    with SASession(store.engine) as session:
        count = BootstrapEngine().run(session)
        session.commit()
    return {"politicians_upserted": count}


@router.post("/admin/politicians", status_code=201)
def create_politician_admin(
    payload: PoliticianCreate,
    x_auth_roles: str | None = Header(default=None),
) -> PoliticianOut:
    """Manually create a politician. Commissioner-only. Use when bootstrap sources are unavailable."""
    roles = [r.strip() for r in (x_auth_roles or "").split(",") if r.strip()]
    if "commissioner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner role required")
    pol = store.create_politician(
        full_name=payload.full_name,
        current_role=payload.current_role,
        role_tier=payload.role_tier,
        party=payload.party,
        jurisdiction=payload.jurisdiction,
        asset_type=payload.asset_type,
        status=payload.status,
        aliases=payload.aliases,
        source=payload.source,
    )
    return PoliticianOut(
        id=pol.id,
        name=pol.full_name,
        full_name=pol.full_name,
        current_role=pol.current_role,
        role_tier=pol.role_tier,
        jurisdiction=pol.jurisdiction,
        asset_type=pol.asset_type,
        party=pol.party,
        status=pol.status,
        aliases=pol.aliases_json if isinstance(pol.aliases_json, list) else [],
        source=pol.source,
        last_verified_at=pol.last_verified_at,
    )


# ── Internal data-source and attribution routes ───────────────────────────────

@router.get("/internal/data-sources")
def list_data_sources(
    bootstrap: bool | None = Query(default=None),
    active: bool | None = Query(default=None),
) -> dict[str, list[DataSourceOut]]:
    sources = store.list_data_sources(bootstrap=bootstrap, active=active)
    return {
        "items": [
            DataSourceOut(
                id=s.id,
                name=s.name,
                source_type=s.source_type,
                bootstrap=s.bootstrap,
                url_template=s.url_template,
                config=s.config_json,
                active=s.active,
                politician_id=s.politician_id,
                created_at=s.created_at,
            )
            for s in sources
        ]
    }


class AttributionRunRequest(BaseModel):
    event_ids: list[str]


@router.post("/internal/attribution/run")
def run_attribution(payload: AttributionRunRequest) -> AttributionRunOut:
    result = store.run_attribution(payload.event_ids)
    return AttributionRunOut(**result)


# ── Story routes ──────────────────────────────────────────────────────────────

class StoryClusterRequest(BaseModel):
    window_hours: int = 24


@router.post("/internal/stories/cluster")
def cluster_stories(payload: StoryClusterRequest = StoryClusterRequest()) -> StoryClusteringRunOut:
    """
    Trigger story clustering for recently ingested articles.
    Groups unclustered PoliticalEventModel rows into canonical NewsStoryModel records.
    Uses AI clustering (Ollama) when ai_enabled=true, falls back to Jaccard heuristic.
    """
    result = store.run_story_clustering(window_hours=payload.window_hours)
    return StoryClusteringRunOut(**result)


@router.post("/internal/stories/rescore")
def rescore_pending_stories(
    x_auth_roles: str | None = Header(default=None),
) -> dict:
    """
    Emit correction ledger entries for all stories flagged rescore_pending=True.
    Stories are re-evaluated with their updated significance. Commissioner-only.
    """
    roles = [r.strip() for r in (x_auth_roles or "").split(",")]
    if "commissioner" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner only")

    stories = store.list_stories(rescore_pending=True)
    total_corrections = 0
    for story in stories:
        if story.scored_week is None:
            continue
        # Trigger re-score via score_league_week for any leagues that scored this story
        # (corrections are emitted automatically by score_league_week when rescore_pending=True)
        # This endpoint just reports counts; actual corrections are emitted at next scoring cycle
        total_corrections += 1
    return {
        "stories_pending_rescore": len(stories),
        "note": "Corrections will be emitted at next scoring cycle or via POST /internal/scoring/run",
    }


@router.get("/stories")
def list_stories(
    status: str | None = None,
    scored: bool | None = None,
    limit: int = 50,
) -> dict:
    """List canonical news stories with optional status/scored filters."""
    stories = store.list_stories(status=status, scored=scored, limit=limit)
    return {
        "items": [
            NewsStoryOut(
                id=s.id,
                canonical_title=s.canonical_title,
                canonical_summary=s.canonical_summary or "",
                event_type=s.event_type,
                jurisdiction=s.jurisdiction,
                significance=s.significance,
                sentiment=s.sentiment,
                is_followup=s.is_followup,
                article_count=s.article_count,
                status=s.status,
                scored=s.scored,
                scored_week=s.scored_week,
                last_scored_significance=s.last_scored_significance,
                score_version=s.score_version,
                rescore_count=s.rescore_count,
                rescore_pending=s.rescore_pending,
                first_seen_at=s.first_seen_at,
                last_updated_at=s.last_updated_at,
            )
            for s in stories
        ],
        "total": len(stories),
    }


@router.get("/stories/{story_id}")
def get_story(story_id: str) -> NewsStoryOut:
    """Get a single canonical news story by ID."""
    story = store.get_story(story_id)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return NewsStoryOut(
        id=story.id,
        canonical_title=story.canonical_title,
        canonical_summary=story.canonical_summary or "",
        event_type=story.event_type,
        jurisdiction=story.jurisdiction,
        significance=story.significance,
        sentiment=story.sentiment,
        is_followup=story.is_followup,
        article_count=story.article_count,
        status=story.status,
        scored=story.scored,
        scored_week=story.scored_week,
        last_scored_significance=story.last_scored_significance,
        score_version=story.score_version,
        rescore_count=story.rescore_count,
        rescore_pending=story.rescore_pending,
        first_seen_at=story.first_seen_at,
        last_updated_at=story.last_updated_at,
    )


def _assert_league_exists(league_id: str):
    league = store.get_league(league_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league
