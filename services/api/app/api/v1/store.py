from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from app.api.v1.schemas import LeagueCreate, TeamCreate


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PoliticalAsset:
    id: str
    name: str
    jurisdiction: str
    asset_type: str


ASSETS: list[PoliticalAsset] = [
    PoliticalAsset("asset-federal-pm", "Prime Minister", "federal", "executive"),
    PoliticalAsset("asset-federal-finance", "Federal Finance Portfolio", "federal", "cabinet"),
    PoliticalAsset("asset-federal-health", "Federal Health Portfolio", "federal", "cabinet"),
    PoliticalAsset("asset-federal-opposition", "Federal Opposition Leader", "federal", "opposition"),
    PoliticalAsset("asset-on-premier", "Premier of Ontario", "ON", "executive"),
    PoliticalAsset("asset-qc-premier", "Premier of Québec", "QC", "executive"),
    PoliticalAsset("asset-bc-premier", "Premier of British Columbia", "BC", "executive"),
    PoliticalAsset("asset-ab-premier", "Premier of Alberta", "AB", "executive"),
    PoliticalAsset("asset-on-health", "Ontario Health Portfolio", "ON", "cabinet"),
    PoliticalAsset("asset-qc-finance", "Québec Finance Portfolio", "QC", "cabinet"),
    PoliticalAsset("asset-bc-environment", "BC Environment Portfolio", "BC", "cabinet"),
    PoliticalAsset("asset-ab-energy", "Alberta Energy Portfolio", "AB", "cabinet"),
]

ROSTER_SLOTS = [
    "federal_lead",
    "federal_cabinet_1",
    "federal_cabinet_2",
    "federal_opposition",
    "provincial_lead_1",
    "provincial_lead_2",
]


@dataclass
class League:
    id: str
    name: str
    format: str
    commissioner_user_id: str
    current_week: int
    created_at: datetime


@dataclass
class Team:
    id: str
    league_id: str
    manager_user_id: str
    name: str
    created_at: datetime


@dataclass
class RosterSlot:
    team_id: str
    slot: str
    asset_id: str


@dataclass
class LedgerEntry:
    id: str
    week: int
    league_id: str
    team_id: str
    event: str
    points: int
    created_at: datetime


@dataclass
class Dispute:
    id: str
    league_id: str
    created_by_user_id: str
    reason: str
    target_entry_id: str | None
    status: str
    created_at: datetime


@dataclass
class AuditLog:
    id: str
    league_id: str
    actor_user_id: str
    action: str
    metadata: dict
    created_at: datetime


@dataclass
class MemoryStore:
    leagues: dict[str, League] = field(default_factory=dict)
    teams: dict[str, Team] = field(default_factory=dict)
    roster_slots: list[RosterSlot] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)
    disputes: dict[str, Dispute] = field(default_factory=dict)
    audit_log: list[AuditLog] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def list_leagues(self) -> list[League]:
        return sorted(self.leagues.values(), key=lambda l: l.created_at)

    def create_league(self, payload: LeagueCreate, commissioner_user_id: str) -> League:
        with self._lock:
            league = League(
                id=f"league-{uuid4().hex[:10]}",
                name=payload.name,
                format=payload.format,
                commissioner_user_id=commissioner_user_id,
                current_week=1,
                created_at=utcnow(),
            )
            self.leagues[league.id] = league
            self._add_audit(league.id, commissioner_user_id, "league.created", {"name": league.name})
            return league

    def get_league(self, league_id: str) -> League | None:
        return self.leagues.get(league_id)

    def list_teams(self, league_id: str) -> list[Team]:
        return [t for t in self.teams.values() if t.league_id == league_id]

    def create_team(self, league_id: str, manager_user_id: str, payload: TeamCreate) -> Team:
        with self._lock:
            team = Team(
                id=f"team-{uuid4().hex[:10]}",
                league_id=league_id,
                manager_user_id=manager_user_id,
                name=payload.name,
                created_at=utcnow(),
            )
            self.teams[team.id] = team
            self._assign_initial_roster(team.id)
            self._add_audit(league_id, manager_user_id, "team.created", {"teamId": team.id, "name": team.name})
            return team

    def roster_for_team(self, team_id: str) -> list[RosterSlot]:
        return [slot for slot in self.roster_slots if slot.team_id == team_id]

    def score_league_week(self, league_id: str) -> tuple[int, int]:
        with self._lock:
            league = self.leagues[league_id]
            teams = self.list_teams(league_id)
            created = 0
            for team in teams:
                slots = self.roster_for_team(team.id)
                for slot in slots:
                    points = self._score_slot(slot.asset_id, league.current_week)
                    self.ledger.append(
                        LedgerEntry(
                            id=f"ledger-{uuid4().hex[:12]}",
                            week=league.current_week,
                            league_id=league_id,
                            team_id=team.id,
                            event=f"weekly.momentum.{slot.slot}",
                            points=points,
                            created_at=utcnow(),
                        )
                    )
                    created += 1

            self._add_audit(
                league_id,
                "system",
                "scoring.week.completed",
                {"week": league.current_week, "entriesCreated": created},
            )
            scored_week = league.current_week
            league.current_week += 1
            return scored_week, created

    def standings(self, league_id: str) -> list[tuple[Team, int]]:
        teams = self.list_teams(league_id)
        totals: dict[str, int] = {t.id: 0 for t in teams}
        for entry in self.ledger:
            if entry.league_id == league_id:
                totals[entry.team_id] = totals.get(entry.team_id, 0) + entry.points
        rows = [(team, totals.get(team.id, 0)) for team in teams]
        rows.sort(key=lambda row: row[1], reverse=True)
        return rows

    def ledger_for_team(self, league_id: str, team_id: str, week: int | None = None) -> list[LedgerEntry]:
        out = [
            entry
            for entry in self.ledger
            if entry.league_id == league_id and entry.team_id == team_id and (week is None or entry.week == week)
        ]
        out.sort(key=lambda e: (e.week, e.created_at), reverse=True)
        return out

    def create_dispute(
        self,
        league_id: str,
        created_by_user_id: str,
        reason: str,
        target_entry_id: str | None,
    ) -> Dispute:
        with self._lock:
            dispute = Dispute(
                id=f"dispute-{uuid4().hex[:10]}",
                league_id=league_id,
                created_by_user_id=created_by_user_id,
                reason=reason,
                target_entry_id=target_entry_id,
                status="open",
                created_at=utcnow(),
            )
            self.disputes[dispute.id] = dispute
            self._add_audit(
                league_id,
                created_by_user_id,
                "dispute.created",
                {"disputeId": dispute.id, "targetEntryId": target_entry_id},
            )
            return dispute

    def resolve_dispute(self, league_id: str, dispute_id: str, actor_user_id: str) -> Dispute | None:
        with self._lock:
            dispute = self.disputes.get(dispute_id)
            if dispute is None or dispute.league_id != league_id:
                return None
            dispute.status = "resolved"
            self._add_audit(league_id, actor_user_id, "dispute.resolved", {"disputeId": dispute.id})
            return dispute

    def list_audit(self, league_id: str) -> list[AuditLog]:
        return [item for item in self.audit_log if item.league_id == league_id]

    def _assign_initial_roster(self, team_id: str) -> None:
        taken = {slot.asset_id for slot in self.roster_slots}
        available = [asset for asset in ASSETS if asset.id not in taken]
        if len(available) < len(ROSTER_SLOTS):
            available = ASSETS

        for idx, slot_name in enumerate(ROSTER_SLOTS):
            asset = available[idx % len(available)]
            self.roster_slots.append(RosterSlot(team_id=team_id, slot=slot_name, asset_id=asset.id))

    @staticmethod
    def _score_slot(asset_id: str, week: int) -> int:
        token = f"{asset_id}:{week}"
        stable = sum(ord(ch) for ch in token)
        return (stable % 9) - 2

    def _add_audit(self, league_id: str, actor_user_id: str, action: str, metadata: dict) -> None:
        self.audit_log.append(
            AuditLog(
                id=f"audit-{uuid4().hex[:12]}",
                league_id=league_id,
                actor_user_id=actor_user_id,
                action=action,
                metadata=metadata,
                created_at=utcnow(),
            )
        )


store = MemoryStore()


def bootstrap_demo_data() -> None:
    if store.list_leagues():
        return
    league = store.create_league(
        LeagueCreate(name="National Strategy League", format="season"),
        commissioner_user_id="demo-user",
    )
    store.create_team(league.id, "demo-user", TeamCreate(name="Ottawa Operators"))
    store.create_team(league.id, "demo-user-2", TeamCreate(name="Provincial Powerhouse"))
    store.score_league_week(league.id)
