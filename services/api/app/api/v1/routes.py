import os

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.v1.schemas import (
    AuditLogOut,
    CabinetCreate,
    CabinetOut,
    CabinetScopeCreate,
    CabinetScopeOut,
    CabinetScopeUpdate,
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
    MandateUpdateOut,
    MandateUpdateRequest,
    MPOut,
    PolicyObjectiveOut,
    PolicySelectionRequest,
    PolicySelectionsOut,
    PoliticalEventOut,
    RosterOut,
    RosterSlotOut,
    ScoringRunOut,
    ScoringRunRequest,
    SeatAssignRequest,
    StandingsOut,
    StandingsRow,
    TeamCreate,
    TeamOut,
    UserCreate,
    UserProfile,
    UserUpdate,
)
from app.api.v1.persistent_store import ASSETS, MPS, POLICY_OBJECTIVES, PORTFOLIO_SEAT_LABELS, roles_for_user, store

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
def list_assets() -> dict[str, list[dict[str, str]]]:
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "jurisdiction": a.jurisdiction,
                "assetType": a.asset_type,
                "party": a.party,
            }
            for a in MPS
        ]
    }

@router.get("/mps")
def list_mps() -> dict[str, list[MPOut]]:
    return {
        "items": [
            MPOut(
                id=mp.id,
                name=mp.name,
                jurisdiction=mp.jurisdiction,
                asset_type=mp.asset_type,
                party=mp.party,
            )
            for mp in MPS
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
    asset_map = {a.id: a for a in MPS}
    return RosterSlotOut(
        roster_slot_id=slot.id,
        slot=slot.slot,
        slot_label=PORTFOLIO_SEAT_LABELS.get(slot.slot, slot.slot),
        asset_id=slot.asset_id,
        asset_name=asset_map[slot.asset_id].name if slot.asset_id in asset_map else slot.asset_id,
        jurisdiction=asset_map[slot.asset_id].jurisdiction if slot.asset_id in asset_map else "unknown",
        asset_type=asset_map[slot.asset_id].asset_type if slot.asset_id in asset_map else "unknown",
        party=asset_map[slot.asset_id].party if slot.asset_id in asset_map else "unknown",
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


def ingest_events(payload: IngestEventsRequest) -> IngestEventsOut:
    received, inserted, duplicates = store.ingest_events(payload.events)
    return IngestEventsOut(received=received, inserted=inserted, duplicates=duplicates)


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
    asset_map = {a.id: a for a in MPS}
    items = [
        RosterSlotOut(
            roster_slot_id=slot.id,
            slot=slot.slot,
            slot_label=PORTFOLIO_SEAT_LABELS.get(slot.slot, slot.slot),
            asset_id=slot.asset_id,
            asset_name=asset_map[slot.asset_id].name if slot.asset_id in asset_map else slot.asset_id,
            jurisdiction=asset_map[slot.asset_id].jurisdiction if slot.asset_id in asset_map else "unknown",
            asset_type=asset_map[slot.asset_id].asset_type if slot.asset_id in asset_map else "unknown",
            party=asset_map[slot.asset_id].party if slot.asset_id in asset_map else "unknown",
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
        StandingsRow(cabinet_id=team.id, cabinet_name=team.name, total_points=total_points, rank=index + 1)
        for index, (team, total_points) in enumerate(ranked)
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


def _assert_league_exists(league_id: str):
    league = store.get_league(league_id)
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league
