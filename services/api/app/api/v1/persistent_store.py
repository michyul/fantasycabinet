from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.api.v1.schemas import LeagueCreate, PoliticalEventIn, TeamCreate


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roles: Mapped[str] = mapped_column(Text, default="manager")
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LeagueModel(Base):
    __tablename__ = "leagues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    format: Mapped[str] = mapped_column(String(20), default="season")
    commissioner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    current_week: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    league_id: Mapped[str] = mapped_column(String(36), ForeignKey("leagues.id"), index=True)
    manager_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RosterSlotModel(Base):
    __tablename__ = "roster_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    slot: Mapped[str] = mapped_column(String(60))
    asset_id: Mapped[str] = mapped_column(String(80), index=True)
    lineup_status: Mapped[str] = mapped_column(String(10), default="active")


class LedgerEntryModel(Base):
    __tablename__ = "score_ledger_entries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    league_id: Mapped[str] = mapped_column(String(36), ForeignKey("leagues.id"), index=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    event: Mapped[str] = mapped_column(String(120))
    points: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PoliticalEventModel(Base):
    __tablename__ = "political_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(80), index=True)
    source_event_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSONB)
    scored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    scored_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DisputeModel(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    league_id: Mapped[str] = mapped_column(String(36), ForeignKey("leagues.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    target_entry_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    league_id: Mapped[str] = mapped_column(String(36), ForeignKey("leagues.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicySelectionModel(Base):
    __tablename__ = "policy_selections"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    objective_id: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@dataclass
class PoliticalAsset:
    id: str
    name: str
    jurisdiction: str
    asset_type: str
    party: str = "independent"


# MPS is the canonical name; ASSETS is kept as alias for backward compat
MPS: list[PoliticalAsset] = [
    # ── Federal – Government (Liberal) ──────────────────────────────────────
    PoliticalAsset("mp-fed-pm",           "Prime Minister",               "federal", "executive",   "Liberal"),
    PoliticalAsset("mp-fed-deputy-pm",    "Deputy Prime Minister",        "federal", "executive",   "Liberal"),
    PoliticalAsset("mp-fed-finance",      "Federal Finance Minister",     "federal", "cabinet",     "Liberal"),
    PoliticalAsset("mp-fed-health",       "Federal Health Minister",      "federal", "cabinet",     "Liberal"),
    PoliticalAsset("mp-fed-justice",      "Federal Justice Minister",     "federal", "cabinet",     "Liberal"),
    PoliticalAsset("mp-fed-environment",  "Federal Environment Minister", "federal", "cabinet",     "Liberal"),
    PoliticalAsset("mp-fed-houseLeader",  "Government House Leader",      "federal", "parliamentary", "Liberal"),
    # ── Federal – Opposition (Conservative) ─────────────────────────────────
    PoliticalAsset("mp-fed-con-leader",   "Conservative Leader",          "federal", "opposition",  "Conservative"),
    PoliticalAsset("mp-fed-con-finance",  "Conservative Finance Critic",  "federal", "opposition",  "Conservative"),
    PoliticalAsset("mp-fed-con-house",    "Conservative House Leader",    "federal", "parliamentary", "Conservative"),
    # ── Federal – NDP ────────────────────────────────────────────────────────
    PoliticalAsset("mp-fed-ndp-leader",   "NDP Leader",                   "federal", "opposition",  "NDP"),
    PoliticalAsset("mp-fed-ndp-finance",  "NDP Finance Critic",           "federal", "opposition",  "NDP"),
    # ── Federal – Bloc Québécois ─────────────────────────────────────────────
    PoliticalAsset("mp-fed-bloc-leader",  "Bloc Québécois Leader",        "federal", "opposition",  "Bloc"),
    # ── Ontario (Conservative provincial) ───────────────────────────────────
    PoliticalAsset("mp-on-premier",       "Premier of Ontario",           "ON",      "executive",   "Conservative"),
    PoliticalAsset("mp-on-finance",       "Ontario Finance Minister",     "ON",      "cabinet",     "Conservative"),
    PoliticalAsset("mp-on-health",        "Ontario Health Minister",      "ON",      "cabinet",     "Conservative"),
    PoliticalAsset("mp-on-opp",           "Ontario Liberal Leader",       "ON",      "opposition",  "Liberal"),
    # ── Québec (CAQ provincial) ──────────────────────────────────────────────
    PoliticalAsset("mp-qc-premier",       "Premier of Québec",            "QC",      "executive",   "CAQ"),
    PoliticalAsset("mp-qc-finance",       "Québec Finance Minister",      "QC",      "cabinet",     "CAQ"),
    PoliticalAsset("mp-qc-opp",           "Québec PQ Leader",             "QC",      "opposition",  "PQ"),
    # ── British Columbia (NDP provincial) ───────────────────────────────────
    PoliticalAsset("mp-bc-premier",       "Premier of British Columbia",  "BC",      "executive",   "NDP"),
    PoliticalAsset("mp-bc-finance",       "BC Finance Minister",          "BC",      "cabinet",     "NDP"),
    PoliticalAsset("mp-bc-opp",           "BC Conservative Leader",       "BC",      "opposition",  "Conservative"),
    # ── Alberta (UCP provincial) ─────────────────────────────────────────────
    PoliticalAsset("mp-ab-premier",       "Premier of Alberta",           "AB",      "executive",   "UCP"),
    PoliticalAsset("mp-ab-finance",       "Alberta Finance Minister",     "AB",      "cabinet",     "UCP"),
    PoliticalAsset("mp-ab-opp",           "Alberta NDP Leader",           "AB",      "opposition",  "NDP"),
    # ── Manitoba (NDP provincial) ────────────────────────────────────────────
    PoliticalAsset("mp-mb-premier",       "Premier of Manitoba",          "MB",      "executive",   "NDP"),
    # ── Nova Scotia (Conservative provincial) ───────────────────────────────
    PoliticalAsset("mp-ns-premier",       "Premier of Nova Scotia",       "NS",      "executive",   "Conservative"),
    # ── Saskatchewan (Conservative provincial) ──────────────────────────────
    PoliticalAsset("mp-sk-premier",       "Premier of Saskatchewan",      "SK",      "executive",   "Conservative"),
]
ASSETS = MPS  # backward-compat alias

# Human-readable display names for portfolio seat keys
PORTFOLIO_SEAT_LABELS: dict[str, str] = {
    "head_of_government":   "Head of Government",
    "federal_portfolio_1":  "Federal Portfolio A",
    "federal_portfolio_2":  "Federal Portfolio B",
    "federal_opposition":   "Federal Opposition",
    "provincial_lead":      "Provincial Executive",
    "provincial_portfolio": "Provincial Portfolio",
}

ROSTER_SLOTS = [
    "head_of_government",
    "federal_portfolio_1",
    "federal_portfolio_2",
    "federal_opposition",
    "provincial_lead",
    "provincial_portfolio",
]
PORTFOLIO_SEATS = ROSTER_SLOTS  # canonical alias


@dataclass
class PolicyObjectiveDef:
    id: str
    name: str
    description: str
    event_types: list[str]
    bonus: int


POLICY_OBJECTIVES: list[PolicyObjectiveDef] = [
    PolicyObjectiveDef("obj-economy",    "Economic Growth",              "Bonus on budget, tax, and economic policy events.",             ["legislative", "policy", "executive"],        2),
    PolicyObjectiveDef("obj-health",     "Healthcare Reform",            "Bonus on health system and public health events.",              ["policy", "executive"],                       2),
    PolicyObjectiveDef("obj-housing",    "Housing & Infrastructure",     "Bonus on housing, construction, and infrastructure events.",    ["policy", "legislative"],                     2),
    PolicyObjectiveDef("obj-climate",    "Climate Action",               "Bonus on environment, energy, and climate events.",             ["policy", "executive", "intergovernmental"],  2),
    PolicyObjectiveDef("obj-fed-prov",   "Federal-Provincial Relations", "Bonus on intergovernmental coordination events.",               ["intergovernmental"],                         3),
    PolicyObjectiveDef("obj-stability",  "Government Stability",         "Bonus on confidence votes and coalition events.",               ["confidence"],                                3),
]

ACTIVE_LINEUP_SIZE = 4
MIN_FEDERAL_ACTIVE = 1
MIN_PROVINCIAL_ACTIVE = 1


def _roles_to_text(roles: list[str]) -> str:
    return ",".join(sorted(set([r.strip() for r in roles if r.strip()]))) or "manager"


def _text_to_roles(text: str) -> list[str]:
    return [r.strip() for r in text.split(",") if r.strip()]


class PersistentStore:
    def __init__(self) -> None:
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://fantasycabinet:fantasycabinet@postgres:5432/fantasycabinet",
        )
        self.engine = create_engine(db_url, pool_pre_ping=True)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE roster_slots ADD COLUMN IF NOT EXISTS lineup_status VARCHAR(10) DEFAULT 'active'"
            )
            connection.exec_driver_sql(
                "UPDATE roster_slots SET lineup_status='active' WHERE lineup_status IS NULL"
            )
            # Rename legacy scope names
            connection.exec_driver_sql(
                "UPDATE leagues SET name = 'National Politics \u2014 2026 Season' "
                "WHERE name IN ('National Strategy League', 'National Strategy League 2026')"
            )
            # Migrate old slot names to canonical names
            connection.exec_driver_sql("""
                UPDATE roster_slots SET slot = CASE slot
                    WHEN 'federal_lead'       THEN 'head_of_government'
                    WHEN 'federal_cabinet_1'  THEN 'federal_portfolio_1'
                    WHEN 'federal_cabinet_2'  THEN 'federal_portfolio_2'
                    WHEN 'provincial_lead_1'  THEN 'provincial_lead'
                    WHEN 'provincial_lead_2'  THEN 'provincial_portfolio'
                    ELSE slot
                END
            """)
            # Migrate old asset IDs to canonical MP IDs
            connection.exec_driver_sql("""
                UPDATE roster_slots SET asset_id = CASE asset_id
                    WHEN 'asset-federal-pm'         THEN 'mp-fed-pm'
                    WHEN 'asset-federal-finance'    THEN 'mp-fed-finance'
                    WHEN 'asset-federal-health'     THEN 'mp-fed-health'
                    WHEN 'asset-federal-justice'    THEN 'mp-fed-justice'
                    WHEN 'asset-federal-opposition' THEN 'mp-fed-con-leader'
                    WHEN 'asset-on-premier'         THEN 'mp-on-premier'
                    WHEN 'asset-qc-premier'         THEN 'mp-qc-premier'
                    WHEN 'asset-bc-premier'         THEN 'mp-bc-premier'
                    WHEN 'asset-ab-premier'         THEN 'mp-ab-premier'
                    WHEN 'asset-mb-premier'         THEN 'mp-mb-premier'
                    ELSE asset_id
                END
            """)
        self._normalize_existing_lineups()

    def _normalize_existing_lineups(self) -> None:
        with Session(self.engine) as session:
            teams = list(session.scalars(select(TeamModel)))
            changed = False
            for team in teams:
                slots = list(
                    session.scalars(
                        select(RosterSlotModel)
                        .where(RosterSlotModel.team_id == team.id)
                        .order_by(RosterSlotModel.id.asc())
                    )
                )
                active_count = sum(1 for slot in slots if slot.lineup_status == "active")
                if active_count == ACTIVE_LINEUP_SIZE:
                    continue
                for idx, slot in enumerate(slots):
                    slot.lineup_status = "active" if idx < ACTIVE_LINEUP_SIZE else "bench"
                changed = True
            if changed:
                session.commit()

    def upsert_user(self, external_subject: str, display_name: str, email: str | None, roles: list[str], issuer: str | None) -> UserModel:
        with Session(self.engine) as session:
            user = session.scalar(select(UserModel).where(UserModel.external_subject == external_subject))
            if user is None:
                user = UserModel(
                    id=f"user-{uuid4().hex[:12]}",
                    external_subject=external_subject,
                    display_name=display_name,
                    email=email,
                    roles=_roles_to_text(roles),
                    issuer=issuer,
                )
                session.add(user)
            else:
                user.display_name = display_name
                user.email = email
                user.roles = _roles_to_text(roles)
                user.issuer = issuer
                user.updated_at = utcnow()
            session.commit()
            session.refresh(user)
            return user

    def list_users(self) -> list[UserModel]:
        with Session(self.engine) as session:
            return list(session.scalars(select(UserModel).order_by(UserModel.created_at.asc())))

    def get_user(self, user_id: str) -> UserModel | None:
        with Session(self.engine) as session:
            return session.get(UserModel, user_id)

    def create_user(
        self,
        display_name: str,
        email: str | None,
        roles: list[str],
        external_subject: str | None = None,
        issuer: str | None = None,
    ) -> UserModel:
        with Session(self.engine) as session:
            subject = external_subject or f"local-{uuid4().hex[:12]}"
            existing = session.scalar(select(UserModel).where(UserModel.external_subject == subject))
            if existing is not None:
                return existing
            user = UserModel(
                id=f"user-{uuid4().hex[:12]}",
                external_subject=subject,
                display_name=display_name,
                email=email,
                roles=_roles_to_text(roles),
                issuer=issuer,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        roles: list[str] | None = None,
    ) -> UserModel | None:
        with Session(self.engine) as session:
            user = session.get(UserModel, user_id)
            if user is None:
                return None
            if display_name is not None:
                user.display_name = display_name
            user.email = email
            if roles is not None:
                user.roles = _roles_to_text(roles)
            user.updated_at = utcnow()
            session.commit()
            session.refresh(user)
            return user

    def list_leagues(self) -> list[LeagueModel]:
        with Session(self.engine) as session:
            return list(session.scalars(select(LeagueModel).order_by(LeagueModel.created_at.asc())))

    def create_league(self, payload: LeagueCreate, commissioner_user_id: str) -> LeagueModel:
        with Session(self.engine) as session:
            league = LeagueModel(
                id=f"league-{uuid4().hex[:10]}",
                name=payload.name,
                format=payload.format,
                commissioner_user_id=commissioner_user_id,
                current_week=1,
                created_at=utcnow(),
            )
            session.add(league)
            session.flush()
            self._add_audit(session, league.id, commissioner_user_id, "league.created", {"name": league.name})
            session.commit()
            session.refresh(league)
            return league

    def get_league(self, league_id: str) -> LeagueModel | None:
        with Session(self.engine) as session:
            return session.get(LeagueModel, league_id)

    def update_league(
        self,
        league_id: str,
        name: str | None = None,
        format: str | None = None,
    ) -> LeagueModel:
        with Session(self.engine) as session:
            league = session.get(LeagueModel, league_id)
            if league is None:
                raise ValueError(f"Cabinet scope {league_id!r} not found")
            if name is not None:
                league.name = name
            if format is not None:
                league.format = format
            session.commit()
            session.refresh(league)
            return league

    def list_teams(self, league_id: str) -> list[TeamModel]:
        with Session(self.engine) as session:
            stmt = select(TeamModel).where(TeamModel.league_id == league_id).order_by(TeamModel.created_at.asc())
            return list(session.scalars(stmt))

    def create_team(self, league_id: str, manager_user_id: str, payload: TeamCreate) -> TeamModel:
        with Session(self.engine) as session:
            team = TeamModel(
                id=f"team-{uuid4().hex[:10]}",
                league_id=league_id,
                manager_user_id=manager_user_id,
                name=payload.name,
                created_at=utcnow(),
            )
            session.add(team)
            session.flush()
            self._assign_initial_roster(session, league_id, team.id)
            self._add_audit(session, league_id, manager_user_id, "team.created", {"teamId": team.id, "name": team.name})
            session.commit()
            session.refresh(team)
            return team

    def roster_for_team(self, team_id: str) -> list[RosterSlotModel]:
        with Session(self.engine) as session:
            stmt = select(RosterSlotModel).where(RosterSlotModel.team_id == team_id).order_by(RosterSlotModel.id.asc())
            return list(session.scalars(stmt))

    def update_lineup(self, team_id: str, updates: list[tuple[int, str]]) -> tuple[int, int] | None:
        with Session(self.engine) as session:
            team = session.get(TeamModel, team_id)
            if team is None:
                return None

            slots = list(session.scalars(select(RosterSlotModel).where(RosterSlotModel.team_id == team_id)))
            slot_map = {slot.id: slot for slot in slots}
            for roster_slot_id, lineup_status in updates:
                slot = slot_map.get(roster_slot_id)
                if slot is None:
                    continue
                slot.lineup_status = lineup_status

            active_count = sum(1 for slot in slots if slot.lineup_status == "active")
            if active_count != ACTIVE_LINEUP_SIZE:
                raise ValueError(f"Mandate configuration must have exactly {ACTIVE_LINEUP_SIZE} governing slots")

            federal_active = 0
            provincial_active = 0
            asset_by_id = {asset.id: asset for asset in ASSETS}
            for slot in slots:
                if slot.lineup_status != "active":
                    continue
                asset = asset_by_id.get(slot.asset_id)
                if asset is None:
                    continue
                if asset.jurisdiction.lower() == "federal":
                    federal_active += 1
                else:
                    provincial_active += 1

            if federal_active < MIN_FEDERAL_ACTIVE:
                raise ValueError("Mandate configuration must include at least one federal governing slot")
            if provincial_active < MIN_PROVINCIAL_ACTIVE:
                raise ValueError("Mandate configuration must include at least one provincial governing slot")

            session.commit()
            return active_count, len(slots) - active_count

    def ingest_events(self, events: list[PoliticalEventIn]) -> tuple[int, int, int]:
        inserted = 0
        duplicates = 0
        with Session(self.engine) as session:
            for event in events:
                normalized_source_event_id = self._normalize_source_event_id(event.source_event_id)
                existing = session.scalar(
                    select(PoliticalEventModel).where(
                        PoliticalEventModel.source_name == event.source_name,
                        PoliticalEventModel.source_event_id == normalized_source_event_id,
                    )
                )
                if existing is not None:
                    duplicates += 1
                    continue

                session.add(
                    PoliticalEventModel(
                        id=f"event-{uuid4().hex[:12]}",
                        source_name=event.source_name,
                        source_event_id=normalized_source_event_id,
                        title=event.title,
                        url=(event.url or "")[:1000] if event.url else None,
                        occurred_at=event.occurred_at,
                        jurisdiction=event.jurisdiction,
                        event_type=event.event_type,
                        payload_json=event.payload,
                        scored=False,
                        scored_week=None,
                        created_at=utcnow(),
                    )
                )
                inserted += 1

            session.commit()
        return len(events), inserted, duplicates

    @staticmethod
    def _normalize_source_event_id(source_event_id: str) -> str:
        if len(source_event_id) <= 255:
            return source_event_id
        digest = hashlib.sha1(source_event_id.encode("utf-8")).hexdigest()
        return f"hash-{digest}"

    def list_events(self, limit: int = 100) -> list[PoliticalEventModel]:
        with Session(self.engine) as session:
            stmt = select(PoliticalEventModel).order_by(PoliticalEventModel.occurred_at.desc()).limit(limit)
            return list(session.scalars(stmt))

    def score_league_week(self, league_id: str) -> tuple[int, int]:
        with Session(self.engine) as session:
            league = session.get(LeagueModel, league_id)
            if league is None:
                raise ValueError("League not found")

            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))
            created = 0
            unscored_events = list(
                session.scalars(
                    select(PoliticalEventModel)
                    .where(PoliticalEventModel.scored.is_(False))
                    .order_by(PoliticalEventModel.occurred_at.asc())
                )
            )

            for team in teams:
                slots = list(session.scalars(select(RosterSlotModel).where(RosterSlotModel.team_id == team.id)))
                active_slots = [slot for slot in slots if slot.lineup_status == "active"]
                # Load this cabinet's active policy objectives for bonus scoring
                policy_sel_rows = list(session.scalars(
                    select(PolicySelectionModel).where(PolicySelectionModel.team_id == team.id)
                ))
                active_objectives = [
                    obj for obj in POLICY_OBJECTIVES
                    if obj.id in {r.objective_id for r in policy_sel_rows}
                ]
                for event in unscored_events:
                    best_points = 0
                    best_slot = None
                    for slot in active_slots:
                        points = self._score_event_for_asset(slot.asset_id, event)
                        if abs(points) > abs(best_points):
                            best_points = points
                            best_slot = slot

                    if best_slot is None or best_points == 0:
                        continue

                    # Policy objective bonus: take the highest matching bonus
                    policy_bonus = max(
                        (obj.bonus for obj in active_objectives if event.event_type in obj.event_types),
                        default=0,
                    )

                    session.add(
                        LedgerEntryModel(
                            id=f"ledger-{uuid4().hex[:12]}",
                            week=league.current_week,
                            league_id=league_id,
                            team_id=team.id,
                            event=f"real_event.{event.event_type}.{best_slot.slot}",
                            points=best_points + policy_bonus,
                            created_at=utcnow(),
                        )
                    )
                    created += 1

            for event in unscored_events:
                event.scored = True
                event.scored_week = league.current_week

            if not unscored_events:
                for team in teams:
                    slots = list(session.scalars(select(RosterSlotModel).where(RosterSlotModel.team_id == team.id)))
                    active_slots = [slot for slot in slots if slot.lineup_status == "active"]
                    for slot in active_slots:
                        points = self._score_slot(slot.asset_id, league.current_week)
                        session.add(
                            LedgerEntryModel(
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
                session,
                league_id,
                "system",
                "scoring.week.completed",
                {
                    "week": league.current_week,
                    "entriesCreated": created,
                    "realEventsProcessed": len(unscored_events),
                },
            )
            scored_week = league.current_week
            league.current_week += 1
            session.commit()
            return scored_week, created

    def standings(self, league_id: str) -> list[tuple[TeamModel, int]]:
        with Session(self.engine) as session:
            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))
            totals: dict[str, int] = {team.id: 0 for team in teams}
            entries = list(session.scalars(select(LedgerEntryModel).where(LedgerEntryModel.league_id == league_id)))
            for entry in entries:
                totals[entry.team_id] = totals.get(entry.team_id, 0) + entry.points
            rows = [(team, totals.get(team.id, 0)) for team in teams]
            rows.sort(key=lambda row: row[1], reverse=True)
            return rows

    def ledger_for_team(self, league_id: str, team_id: str, week: int | None = None) -> list[LedgerEntryModel]:
        with Session(self.engine) as session:
            stmt = select(LedgerEntryModel).where(
                LedgerEntryModel.league_id == league_id,
                LedgerEntryModel.team_id == team_id,
            )
            if week is not None:
                stmt = stmt.where(LedgerEntryModel.week == week)
            stmt = stmt.order_by(LedgerEntryModel.week.desc(), LedgerEntryModel.created_at.desc())
            return list(session.scalars(stmt))

    def create_dispute(self, league_id: str, created_by_user_id: str, reason: str, target_entry_id: str | None) -> DisputeModel:
        with Session(self.engine) as session:
            dispute = DisputeModel(
                id=f"dispute-{uuid4().hex[:10]}",
                league_id=league_id,
                created_by_user_id=created_by_user_id,
                reason=reason,
                target_entry_id=target_entry_id,
                status="open",
                created_at=utcnow(),
            )
            session.add(dispute)
            self._add_audit(
                session,
                league_id,
                created_by_user_id,
                "dispute.created",
                {"disputeId": dispute.id, "targetEntryId": target_entry_id},
            )
            session.commit()
            session.refresh(dispute)
            return dispute

    def resolve_dispute(self, league_id: str, dispute_id: str, actor_user_id: str) -> DisputeModel | None:
        with Session(self.engine) as session:
            dispute = session.get(DisputeModel, dispute_id)
            if dispute is None or dispute.league_id != league_id:
                return None
            dispute.status = "resolved"
            self._add_audit(session, league_id, actor_user_id, "dispute.resolved", {"disputeId": dispute.id})
            session.commit()
            session.refresh(dispute)
            return dispute

    def list_audit(self, league_id: str) -> list[AuditLogModel]:
        with Session(self.engine) as session:
            stmt = select(AuditLogModel).where(AuditLogModel.league_id == league_id).order_by(AuditLogModel.created_at.desc())
            return list(session.scalars(stmt))

    def _assign_initial_roster(self, session: Session, league_id: str, team_id: str) -> None:
        used_asset_rows = session.execute(
            select(RosterSlotModel.asset_id)
            .join(TeamModel, TeamModel.id == RosterSlotModel.team_id)
            .where(TeamModel.league_id == league_id)
        ).all()
        used_asset_ids = {row[0] for row in used_asset_rows}
        available = [asset for asset in ASSETS if asset.id not in used_asset_ids]
        if len(available) < len(ROSTER_SLOTS):
            available = ASSETS

        for idx, slot_name in enumerate(ROSTER_SLOTS):
            asset = available[idx % len(available)]
            default_status = "active" if idx < 4 else "bench"
            session.add(RosterSlotModel(team_id=team_id, slot=slot_name, asset_id=asset.id, lineup_status=default_status))

    def assign_mp_to_seat(self, team_id: str, slot_name: str, mp_id: str) -> RosterSlotModel:
        mp = next((a for a in ASSETS if a.id == mp_id), None)
        if mp is None:
            raise ValueError(f"MP {mp_id!r} not found in pool")
        with Session(self.engine) as session:
            team = session.get(TeamModel, team_id)
            if team is None:
                raise ValueError("Cabinet not found")
            slot = session.scalar(
                select(RosterSlotModel)
                .where(RosterSlotModel.team_id == team_id, RosterSlotModel.slot == slot_name)
            )
            if slot is None:
                raise ValueError(f"Portfolio seat {slot_name!r} not found in cabinet")
            slot.asset_id = mp_id
            session.commit()
            session.refresh(slot)
            return slot

    def list_policy_objectives(self) -> list[PolicyObjectiveDef]:
        return POLICY_OBJECTIVES

    def get_cabinet_policy_objectives(self, team_id: str) -> list[str]:
        with Session(self.engine) as session:
            rows = list(session.scalars(
                select(PolicySelectionModel).where(PolicySelectionModel.team_id == team_id)
            ))
            return [row.objective_id for row in rows]

    def set_cabinet_policy_objectives(self, team_id: str, objective_ids: list[str]) -> list[str]:
        MAX_OBJECTIVES = 2
        valid_ids = {obj.id for obj in POLICY_OBJECTIVES}
        filtered = [oid for oid in objective_ids if oid in valid_ids][:MAX_OBJECTIVES]
        with Session(self.engine) as session:
            existing = list(session.scalars(
                select(PolicySelectionModel).where(PolicySelectionModel.team_id == team_id)
            ))
            for row in existing:
                session.delete(row)
            session.flush()
            for oid in filtered:
                session.add(PolicySelectionModel(
                    id=f"psel-{uuid4().hex[:12]}",
                    team_id=team_id,
                    objective_id=oid,
                    created_at=utcnow(),
                ))
            session.commit()
        return filtered

    @staticmethod
    def _score_slot(asset_id: str, week: int) -> int:
        token = f"{asset_id}:{week}"
        stable = sum(ord(ch) for ch in token)
        return (stable % 9) - 2

    @staticmethod
    def _score_event_for_asset(asset_id: str, event: PoliticalEventModel) -> int:
        asset = next((a for a in MPS if a.id == asset_id), None)
        if asset is None:
            return 0

        event_jurisdiction = (event.jurisdiction or "federal").upper()
        asset_jurisdiction = (asset.jurisdiction or "federal").upper()

        # Jurisdiction gate: provincial MPs only score provincial events in their province;
        # federal MPs score federal events and intergovernmental events.
        if asset_jurisdiction not in {"FEDERAL"} and asset_jurisdiction != event_jurisdiction:
            # Allow intergovernmental events to score for all jurisdictions
            if event.event_type != "intergovernmental":
                return 0
        if asset_jurisdiction == "FEDERAL" and event_jurisdiction not in {"FEDERAL", "CANADA"}:
            if event.event_type != "intergovernmental":
                return 0

        # Base points by event category (aligned with scoring-model.md)
        base_by_type: dict[str, int] = {
            "legislative":       5,
            "executive":         4,
            "intergovernmental": 5,
            "opposition":        3,
            "election":          4,
            "ethics":           -6,
            "confidence":        6,   # confidence votes are high-stakes
            "policy":            4,
            "general":           2,
        }
        base = base_by_type.get(event.event_type, 2)

        # Role affinity bonus: does this MP's role align with the event category?
        affinity = 0
        if asset.asset_type in {"executive"} and event.event_type in {"executive", "intergovernmental", "confidence", "policy"}:
            affinity = 3
        elif asset.asset_type == "cabinet" and event.event_type in {"legislative", "policy", "executive"}:
            affinity = 2
        elif asset.asset_type == "opposition" and event.event_type in {"opposition", "legislative", "ethics", "confidence"}:
            affinity = 2
        elif asset.asset_type == "parliamentary" and event.event_type in {"legislative", "confidence"}:
            affinity = 2
        elif event.event_type == "general":
            affinity = 1

        # Party affinity: if the event title mentions the MP's party, bonus
        title_lower = (event.title or "").lower()
        party_lower = asset.party.lower()
        party_bonus = 0
        if party_lower in title_lower and party_lower not in {"independent"}:
            party_bonus = 2

        # Negative event penalties
        penalty = 0
        if any(token in title_lower for token in ["resign", "scandal", "ethics violation", "investigation", "fired", "ousted"]):
            penalty = 3
        if event.event_type == "ethics":
            penalty = max(penalty, 2)

        # Confidence defeat is very bad for governing MPs
        if event.event_type == "confidence" and "defeat" in title_lower:
            if asset.asset_type in {"executive", "cabinet", "parliamentary"} and asset.jurisdiction == "federal":
                base = -8

        score = base + affinity + party_bonus - penalty

        # Cap per scoring-model.md
        return max(-8, min(8, score))

    @staticmethod
    def _add_audit(session: Session, league_id: str, actor_user_id: str, action: str, metadata: dict) -> None:
        PersistentStore._ensure_actor_user(session, actor_user_id)
        session.add(
            AuditLogModel(
                id=f"audit-{uuid4().hex[:12]}",
                league_id=league_id,
                actor_user_id=actor_user_id,
                action=action,
                metadata_json=metadata,
                created_at=utcnow(),
            )
        )

    @staticmethod
    def _ensure_actor_user(session: Session, actor_user_id: str) -> None:
        actor = session.get(UserModel, actor_user_id)
        if actor is not None:
            return
        session.add(
            UserModel(
                id=actor_user_id,
                external_subject=actor_user_id,
                display_name="System",
                email=None,
                roles="system",
                issuer=None,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        session.flush()


store = PersistentStore()


def bootstrap_demo_data() -> None:
    store.init_db()
    if store.list_leagues():
        return

    demo_user = store.upsert_user(
        external_subject="demo-user",
        display_name="Demo Manager",
        email="demo@example.com",
        roles=["manager", "commissioner"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    second_user = store.upsert_user(
        external_subject="demo-user-2",
        display_name="Second Manager",
        email="manager2@example.com",
        roles=["manager"],
        issuer=os.getenv("OIDC_ISSUER"),
    )
    scope = store.create_league(
        LeagueCreate(name="National Politics — 2026 Season", format="season"),
        commissioner_user_id=demo_user.id,
    )
    store.create_team(scope.id, demo_user.id, TeamCreate(name="Federal Strategy Cabinet"))
    store.create_team(scope.id, second_user.id, TeamCreate(name="Provincial Focus Cabinet"))
    store.score_league_week(scope.id)


def roles_for_user(user: UserModel) -> list[str]:
    return _text_to_roles(user.roles)
