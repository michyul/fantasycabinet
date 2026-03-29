from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, select
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
    attribution_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    politician_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    story_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # FK to news_stories
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
    story_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # FK to news_stories
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


class PoliticianModel(Base):
    """A real politician tracked by the platform. Seeded by BootstrapEngine."""
    __tablename__ = "politicians"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)   # e.g. pol-mark-carney
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    aliases_json: Mapped[dict] = mapped_column("aliases", JSONB, default=list)
    current_role: Mapped[str] = mapped_column(String(300), default="")
    role_tier: Mapped[int] = mapped_column(Integer, default=5)       # 1=PM/Premier … 5=backbench
    party: Mapped[str] = mapped_column(String(80), default="independent")
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)  # federal|ON|QC|BC|AB|…
    asset_type: Mapped[str] = mapped_column(String(40), default="parliamentary")  # executive|cabinet|opposition|parliamentary
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # active|pending|ineligible|retired
    source: Mapped[str] = mapped_column(String(40), default="bootstrap")   # ourcommons|wikidata|curated|admin
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PoliticianRoleHistoryModel(Base):
    """Tracks every role change for a politician (for scoring leadership_change events)."""
    __tablename__ = "politician_role_history"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    politician_id: Mapped[str] = mapped_column(String(80), ForeignKey("politicians.id"), index=True)
    previous_role: Mapped[str] = mapped_column(String(300), default="")
    new_role: Mapped[str] = mapped_column(String(300), default="")
    previous_tier: Mapped[int] = mapped_column(Integer, default=5)
    new_tier: Mapped[int] = mapped_column(Integer, default=5)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    changed_by_user_id: Mapped[str] = mapped_column(String(36), default="system")


class EventAttributionModel(Base):
    """Records which politician was attributed to a political event."""
    __tablename__ = "event_attributions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(40), ForeignKey("political_events.id"), index=True)
    politician_id: Mapped[str] = mapped_column(String(80), ForeignKey("politicians.id"), index=True)
    attribution_type: Mapped[str] = mapped_column(String(20))  # direct_name|alias|role_title|system
    confidence: Mapped[float] = mapped_column(Float)
    matched_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataSourceModel(Base):
    """Feed or API source used by the worker and the bootstrap engine."""
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)  # rss|ourcommons_api|wikidata_sparql|legislature_html
    bootstrap: Mapped[bool] = mapped_column(Boolean, default=False)   # True = used by BootstrapEngine
    url_template: Mapped[str] = mapped_column(Text)
    config_json: Mapped[dict] = mapped_column("config", JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    politician_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)  # per-politician RSS
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoringRuleModel(Base):
    """DB-managed scoring rules consumed by ScoringEngine."""
    __tablename__ = "scoring_rules"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rule_version: Mapped[str] = mapped_column(String(20), default="v1", index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    asset_type: Mapped[str] = mapped_column(String(40))
    base_points: Mapped[int] = mapped_column(Integer)
    affinity_bonus: Mapped[int] = mapped_column(Integer, default=0)
    jurisdiction_scope: Mapped[str] = mapped_column(String(10), default="own")  # own|any
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SystemConfigModel(Base):
    """Runtime configuration key/value store (AI settings, scoring params, etc.)."""
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict] = mapped_column("value", JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str] = mapped_column(String(36), default="system")


class RoleClassificationModel(Base):
    """Pattern → (tier, asset_type) rules used by BootstrapEngine's RoleClassifier."""
    __tablename__ = "role_classifications"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pattern: Mapped[str] = mapped_column(String(120), index=True)  # lowercase substring to match
    tier: Mapped[int] = mapped_column(Integer)
    asset_type: Mapped[str] = mapped_column(String(40))
    jurisdiction_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)  # federal|provincial|None
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)   # higher = checked first
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ManagerStatsModel(Base):
    """Per-user, per-league streak tracking."""
    __tablename__ = "manager_stats"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    league_id: Mapped[str] = mapped_column(String(36), ForeignKey("leagues.id"), index=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True, unique=True)
    participation_streak: Mapped[int] = mapped_column(Integer, default=0)
    positive_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_participation_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_positive_streak: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AchievementModel(Base):
    """Earned achievements for a cabinet."""
    __tablename__ = "achievements"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    achievement_id: Mapped[str] = mapped_column(String(40), index=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    week: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class NewsStoryModel(Base):
    """
    A canonical news story derived from clustering multiple raw PoliticalEventModel
    articles. This is the unit of scoring — not individual articles.

    Lifecycle: active → settling → archived
    Scoring:   scored=False → scored=True (+ corrections via rescore_pending)
    """
    __tablename__ = "news_stories"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)   # story-{sha1[:16]}
    canonical_title: Mapped[str] = mapped_column(Text, index=True)
    canonical_summary: Mapped[str] = mapped_column(Text, default="")
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)
    significance: Mapped[float] = mapped_column(Float)              # 1–10, AI or heuristic
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)    # −1 to +1
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False)  # follow-up coverage → 50% points
    article_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active|settling|archived
    scored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    scored_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_scored_significance: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_version: Mapped[int] = mapped_column(Integer, default=0)  # incremented on each rescore
    rescore_count: Mapped[int] = mapped_column(Integer, default=0)  # max 3
    rescore_pending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Hardcoded game-structure constants (not politician data) ──────────────────
# These define the SHAPE of a cabinet, not who is in it.
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
            # Legacy column migrations
            connection.exec_driver_sql(
                "ALTER TABLE roster_slots ADD COLUMN IF NOT EXISTS lineup_status VARCHAR(10) DEFAULT 'active'"
            )
            connection.exec_driver_sql(
                "UPDATE roster_slots SET lineup_status='active' WHERE lineup_status IS NULL"
            )
            # New ledger columns for attribution linkage
            connection.exec_driver_sql(
                "ALTER TABLE score_ledger_entries ADD COLUMN IF NOT EXISTS attribution_id VARCHAR(40)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE score_ledger_entries ADD COLUMN IF NOT EXISTS politician_id VARCHAR(80)"
            )
            # story_id for full pipeline traceability
            connection.exec_driver_sql(
                "ALTER TABLE score_ledger_entries ADD COLUMN IF NOT EXISTS story_id VARCHAR(40)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE political_events ADD COLUMN IF NOT EXISTS story_id VARCHAR(40)"
            )
            # Seed max_story_points if not present
            connection.exec_driver_sql(
                "INSERT INTO system_config (key, value, updated_at, updated_by) "
                "VALUES ('max_story_points', '15', NOW(), 'system') "
                "ON CONFLICT (key) DO NOTHING"
            )
            connection.exec_driver_sql(
                "INSERT INTO system_config (key, value, updated_at, updated_by) "
                "VALUES ('story_rescore_threshold', '1.5', NOW(), 'system') "
                "ON CONFLICT (key) DO NOTHING"
            )
            # Seed week_modifiers parliamentary calendar if not present
            connection.exec_driver_sql(
                "INSERT INTO system_config (key, value, updated_at, updated_by) "
                "VALUES ('week_modifiers', "
                "'{\"3\": {\"label\": \"Budget Week\", \"description\": \"The federal budget drops — policy and executive events score higher.\", \"multipliers\": {\"policy\": 1.5, \"executive\": 1.3}, \"asset_multipliers\": {}}, "
                "\"7\": {\"label\": \"Opposition Day\", \"description\": \"Opposition gets the floor — opposition asset types score 50%% more.\", \"multipliers\": {}, \"asset_multipliers\": {\"opposition\": 1.5}}, "
                "\"10\": {\"label\": \"Prorogation\", \"description\": \"Parliament is prorogued — only parliamentary events score.\", \"multipliers\": {}, \"asset_multipliers\": {}, \"event_type_whitelist\": [\"parliamentary\", \"intergovernmental\"]}}',"
                " NOW(), 'system') "
                "ON CONFLICT (key) DO NOTHING"
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
        # Run bootstrap engine (idempotent — seeds config tables and fetches politicians if DB empty)
        try:
            from app.api.v1.bootstrap_engine import BootstrapEngine
            with Session(self.engine) as session:
                count = BootstrapEngine().run(session)
                session.commit()
                if count:
                    import logging
                    logging.getLogger(__name__).info("BootstrapEngine seeded %d politicians", count)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("BootstrapEngine skipped during init_db: %s", exc)
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

            # Jurisdiction validation — query politicians from DB
            active_asset_ids = [slot.asset_id for slot in slots if slot.lineup_status == "active"]
            politicians = {
                p.id: p for p in session.scalars(
                    select(PoliticianModel).where(PoliticianModel.id.in_(active_asset_ids))
                )
            }
            federal_active = sum(
                1 for aid in active_asset_ids
                if politicians.get(aid) and politicians[aid].jurisdiction.lower() == "federal"
            )
            provincial_active = active_count - federal_active

            if federal_active < MIN_FEDERAL_ACTIVE:
                raise ValueError("Mandate configuration must include at least one federal governing slot")
            if provincial_active < MIN_PROVINCIAL_ACTIVE:
                raise ValueError("Mandate configuration must include at least one provincial governing slot")

            session.commit()
            self._add_audit_direct(
                team.league_id,
                team.manager_user_id,
                "team.mandate.updated",
                {"teamId": team_id, "activeSlotsCount": active_count},
            )
            return active_count, len(slots) - active_count

    def ingest_events(self, events: list[PoliticalEventIn]) -> tuple[int, int, int, list[str]]:
        inserted = 0
        duplicates = 0
        inserted_ids: list[str] = []
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

                new_id = f"event-{uuid4().hex[:12]}"
                session.add(
                    PoliticalEventModel(
                        id=new_id,
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
                inserted_ids.append(new_id)

            session.commit()
        return len(events), inserted, duplicates, inserted_ids

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
        """
        Score all unscored stories (and correction re-scores) for the given league.

        Pipeline:
          1. Score new stories (scored=False) via ScoringEngine.score_teams_for_stories()
          2. Emit correction entries for stories with rescore_pending=True
          3. Fall back to deterministic momentum when no stories exist

        Returns (scored_week, ledger_entries_created).
        """
        from app.api.v1.ai_client import AIClient
        from app.api.v1.scoring_engine import ScoringEngine

        with Session(self.engine) as session:
            league = session.get(LeagueModel, league_id)
            if league is None:
                raise ValueError("League not found")

            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))
            created = 0

            # Load policy objectives per team
            policy_objectives_by_team: dict[str, list] = {}
            for team in teams:
                sel_rows = list(session.scalars(
                    select(PolicySelectionModel).where(PolicySelectionModel.team_id == team.id)
                ))
                selected_ids = {r.objective_id for r in sel_rows}
                policy_objectives_by_team[team.id] = [
                    obj for obj in POLICY_OBJECTIVES if obj.id in selected_ids
                ]

            config = self.get_system_config()
            ai_client = AIClient.from_config(config) if config.get("ai_enabled") else None
            story_cap = int(config.get("max_story_points", 15))
            week = league.current_week

            scoring_engine = ScoringEngine(
                session=session,
                ai_client=ai_client,
                max_points_per_asset=int(config.get("max_points_per_asset_week", 25)),
                min_points_per_asset=int(config.get("min_points_per_asset_week", -20)),
                ai_confidence_weight=float(config.get("ai_confidence_weight", 0.3)),
            )

            # ── 1. Score new unscored stories ──────────────────────────────────
            unscored_stories = list(
                session.scalars(
                    select(NewsStoryModel)
                    .where(
                        NewsStoryModel.scored.is_(False),
                        NewsStoryModel.status.in_(["active", "settling"]),
                    )
                    .order_by(NewsStoryModel.first_seen_at.asc())
                )
            )

            if unscored_stories:
                results = scoring_engine.score_teams_for_stories(
                    league_id=league_id,
                    week=week,
                    teams=teams,
                    stories=unscored_stories,
                    policy_objectives_by_team=policy_objectives_by_team,
                    story_max_points=story_cap,
                )
                for result in results:
                    session.add(
                        LedgerEntryModel(
                            id=result.ledger_id,
                            week=week,
                            league_id=league_id,
                            team_id=result.team_id,
                            event=f"story.{result.event_type}.{result.slot_name}",
                            points=result.final_points,
                            attribution_id=result.attribution_id,
                            politician_id=result.politician_id,
                            story_id=result.story_id,
                            created_at=utcnow(),
                        )
                    )
                    created += 1

                # Mark all scored
                for story in unscored_stories:
                    story.scored = True
                    story.scored_week = week
                    story.last_scored_significance = story.significance
                    story.rescore_pending = False

            # ── 2. Emit corrections for re-scored stories ─────────────────────
            rescore_stories = list(
                session.scalars(
                    select(NewsStoryModel)
                    .where(
                        NewsStoryModel.scored.is_(True),
                        NewsStoryModel.rescore_pending.is_(True),
                        NewsStoryModel.rescore_count < 3,
                    )
                )
            )

            for story in rescore_stories:
                corrections = scoring_engine.rescore_story_corrections(
                    league_id=league_id,
                    week=week,
                    teams=teams,
                    story=story,
                    policy_objectives_by_team=policy_objectives_by_team,
                    story_max_points=story_cap,
                )
                for corr in corrections:
                    session.add(
                        LedgerEntryModel(
                            id=corr.ledger_id,
                            week=week,
                            league_id=league_id,
                            team_id=corr.team_id,
                            event=f"story.correction.{story.event_type}",
                            points=corr.final_points,
                            attribution_id=corr.attribution_id,
                            politician_id=corr.politician_id,
                            story_id=story.id,
                            created_at=utcnow(),
                        )
                    )
                    created += 1

                story.rescore_count += 1
                story.score_version += 1
                story.last_scored_significance = story.significance
                story.rescore_pending = False

            # ── 3. Also handle ineligibility penalties ────────────────────────
            penalties = scoring_engine.score_ineligibility_penalties(
                league_id=league_id,
                week=week,
                teams=teams,
            )
            for pen in penalties:
                session.add(
                    LedgerEntryModel(
                        id=pen.ledger_id,
                        week=week,
                        league_id=league_id,
                        team_id=pen.team_id,
                        event=f"penalty.ineligibility.{pen.slot_name}",
                        points=pen.final_points,
                        politician_id=pen.politician_id,
                        created_at=utcnow(),
                    )
                )
                created += 1

            # ── 4. Fallback: deterministic momentum when no stories exist ─────
            if not unscored_stories and not rescore_stories:
                # Also check for any legacy unscored raw events (backward compat)
                legacy_events = list(
                    session.scalars(
                        select(PoliticalEventModel)
                        .where(PoliticalEventModel.scored.is_(False))
                        .order_by(PoliticalEventModel.occurred_at.asc())
                    )
                )
                if legacy_events:
                    legacy_results = scoring_engine.score_teams_for_events(
                        league_id=league_id,
                        week=week,
                        teams=teams,
                        events=legacy_events,
                        policy_objectives_by_team=policy_objectives_by_team,
                    )
                    for result in legacy_results:
                        session.add(
                            LedgerEntryModel(
                                id=result.ledger_id,
                                week=week,
                                league_id=league_id,
                                team_id=result.team_id,
                                event=f"real_event.{result.event_type}.{result.slot_name}",
                                points=result.final_points,
                                attribution_id=result.attribution_id,
                                politician_id=result.politician_id,
                                created_at=utcnow(),
                            )
                        )
                        created += 1
                    for event in legacy_events:
                        event.scored = True
                        event.scored_week = week
                else:
                    # Pure momentum fallback when no events at all
                    for team in teams:
                        slots = list(session.scalars(
                            select(RosterSlotModel).where(
                                RosterSlotModel.team_id == team.id,
                                RosterSlotModel.lineup_status == "active",
                            )
                        ))
                        for slot in slots:
                            session.add(
                                LedgerEntryModel(
                                    id=f"ledger-{uuid4().hex[:12]}",
                                    week=week,
                                    league_id=league_id,
                                    team_id=team.id,
                                    event=f"weekly.momentum.{slot.slot}",
                                    points=self._score_slot(slot.asset_id, week),
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
                    "week": week,
                    "entriesCreated": created,
                    "storiesScored": len(unscored_stories),
                    "correctionsEmitted": len(rescore_stories),
                },
            )
            scored_week = league.current_week
            league.current_week += 1
            session.commit()

        # Post-scoring: update streaks and evaluate achievements
        self._update_streaks(league_id, scored_week)
        self._evaluate_achievements(league_id, scored_week)
        return scored_week, created

    def _update_streaks(self, league_id: str, scored_week: int) -> None:
        """Update participation and positive streaks for every team in the league after a scoring cycle."""
        with Session(self.engine) as session:
            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))

            # Determine the cutoff: mandate changes must have occurred after the previous
            # scoring cycle completed (or from the epoch if this is the first cycle).
            last_scoring_at: datetime | None = session.scalar(
                select(AuditLogModel.created_at)
                .where(
                    AuditLogModel.league_id == league_id,
                    AuditLogModel.action == "scoring.week.completed",
                )
                .order_by(AuditLogModel.created_at.desc())
                .limit(1)
            )
            epoch = datetime.min.replace(tzinfo=timezone.utc)
            cutoff = last_scoring_at or epoch

            for team in teams:
                # Participation: did manager make a mandate/portfolio change since the last scoring cycle?
                mandate_change_count = session.scalar(
                    select(func.count(AuditLogModel.id)).where(
                        AuditLogModel.league_id == league_id,
                        AuditLogModel.actor_user_id == team.manager_user_id,
                        AuditLogModel.action == "team.mandate.updated",
                        AuditLogModel.created_at > cutoff,
                    )
                ) or 0
                # Positive streak: did the team score > 0 this week?
                week_total = session.scalar(
                    select(func.coalesce(func.sum(LedgerEntryModel.points), 0)).where(
                        LedgerEntryModel.league_id == league_id,
                        LedgerEntryModel.team_id == team.id,
                        LedgerEntryModel.week == scored_week,
                    )
                ) or 0

                stats = session.scalar(
                    select(ManagerStatsModel).where(ManagerStatsModel.team_id == team.id)
                )
                if stats is None:
                    stats = ManagerStatsModel(
                        id=f"stats-{uuid4().hex[:12]}",
                        user_id=team.manager_user_id,
                        league_id=league_id,
                        team_id=team.id,
                        participation_streak=0,
                        positive_streak=0,
                        longest_participation_streak=0,
                        longest_positive_streak=0,
                        updated_at=utcnow(),
                    )
                    session.add(stats)

                if mandate_change_count > 0:
                    stats.participation_streak += 1
                else:
                    stats.participation_streak = 0
                if stats.participation_streak > stats.longest_participation_streak:
                    stats.longest_participation_streak = stats.participation_streak

                if week_total > 0:
                    stats.positive_streak += 1
                else:
                    stats.positive_streak = 0
                if stats.positive_streak > stats.longest_positive_streak:
                    stats.longest_positive_streak = stats.positive_streak

                stats.updated_at = utcnow()

            session.commit()

    # ── Achievement definitions ───────────────────────────────────────────────
    ACHIEVEMENT_DEFS: list[dict] = [
        {"id": "qp-mvp",             "name": "Question Period MVP",     "description": "One of your MPs dominated the week"},
        {"id": "confidence-supply",  "name": "Confidence & Supply",     "description": "Carried by a single performer"},
        {"id": "ethics-commissioner","name": "Ethics Commissioner",     "description": "Sometimes the news isn't good"},
        {"id": "premiers-conference","name": "Premier's Conference",    "description": "Your provincial picks paid off together"},
        {"id": "shadow-cabinet",     "name": "Shadow Cabinet",          "description": "Strength from the backbench"},
        {"id": "first-blood",        "name": "First Blood",             "description": "Welcome to the game"},
        {"id": "iron-streak-3",      "name": "Iron Streak (3)",         "description": "Three in a row"},
        {"id": "iron-streak-5",      "name": "Iron Streak (5)",         "description": "Unstoppable momentum"},
        {"id": "comeback-kid",       "name": "Comeback Kid",            "description": "From the bottom to the top"},
        {"id": "full-house",         "name": "Full House",              "description": "Everyone delivered"},
    ]

    def _already_earned(self, session: Session, team_id: str, achievement_id: str) -> bool:
        return session.scalar(
            select(func.count(AchievementModel.id)).where(
                AchievementModel.team_id == team_id,
                AchievementModel.achievement_id == achievement_id,
            )
        ) > 0

    def _grant_achievement(
        self,
        session: Session,
        team_id: str,
        achievement_id: str,
        week: int,
        metadata: dict,
    ) -> AchievementModel:
        ach = AchievementModel(
            id=f"ach-{uuid4().hex[:12]}",
            team_id=team_id,
            achievement_id=achievement_id,
            earned_at=utcnow(),
            week=week,
            metadata_json=metadata,
        )
        session.add(ach)
        return ach

    def _evaluate_achievements(self, league_id: str, scored_week: int) -> list[str]:
        """Evaluate all achievement conditions for each team and grant new ones."""
        newly_earned: list[str] = []
        with Session(self.engine) as session:
            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))

            for team in teams:
                team_id = team.id

                # All ledger entries for this team this week
                week_entries = list(session.scalars(
                    select(LedgerEntryModel).where(
                        LedgerEntryModel.team_id == team_id,
                        LedgerEntryModel.week == scored_week,
                    )
                ))
                week_total = sum(e.points for e in week_entries)

                # Per-politician scores this week (aggregate by politician_id)
                pol_scores: dict[str, int] = {}
                for e in week_entries:
                    if e.politician_id:
                        pol_scores[e.politician_id] = pol_scores.get(e.politician_id, 0) + e.points

                # Active roster slots
                active_slots = list(session.scalars(
                    select(RosterSlotModel).where(
                        RosterSlotModel.team_id == team_id,
                        RosterSlotModel.lineup_status == "active",
                    )
                ))
                active_pol_ids = {s.asset_id for s in active_slots}

                # All-time ledger for this team (for first-blood)
                all_time_total = session.scalar(
                    select(func.coalesce(func.sum(LedgerEntryModel.points), 0)).where(
                        LedgerEntryModel.team_id == team_id
                    )
                ) or 0

                # ── qp-mvp: any politician scores 20+ in a single week ────────
                if not self._already_earned(session, team_id, "qp-mvp"):
                    top_pol = max(pol_scores.values(), default=0)
                    if top_pol >= 20:
                        top_pol_id = max(pol_scores, key=lambda k: pol_scores[k])
                        pol_name = session.scalar(
                            select(PoliticianModel.full_name).where(PoliticianModel.id == top_pol_id)
                        ) or top_pol_id
                        newly_earned.append("qp-mvp")
                        self._grant_achievement(session, team_id, "qp-mvp", scored_week,
                                                {"politicianId": top_pol_id, "politicianName": pol_name, "points": top_pol})

                # ── confidence-supply: win week where only 1 active MP scored positive ──
                if not self._already_earned(session, team_id, "confidence-supply"):
                    active_positive = [pid for pid in active_pol_ids if pol_scores.get(pid, 0) > 0]
                    if len(active_positive) == 1:
                        newly_earned.append("confidence-supply")
                        self._grant_achievement(session, team_id, "confidence-supply", scored_week,
                                                {"politicianId": active_positive[0]})

                # ── ethics-commissioner: ethics-type event attributed to MP ──
                if not self._already_earned(session, team_id, "ethics-commissioner"):
                    ethics_entry = next(
                        (e for e in week_entries if "ethics" in (e.event or "").lower()), None
                    )
                    if ethics_entry:
                        newly_earned.append("ethics-commissioner")
                        self._grant_achievement(session, team_id, "ethics-commissioner", scored_week,
                                                {"eventKey": ethics_entry.event})

                # ── premiers-conference: 2+ provincial active MPs all score positive same week ──
                if not self._already_earned(session, team_id, "premiers-conference"):
                    provincial_active_pols = []
                    for s in active_slots:
                        pol = session.get(PoliticianModel, s.asset_id)
                        if pol and pol.jurisdiction.lower() != "federal":
                            provincial_active_pols.append(s.asset_id)
                    prov_positive = [pid for pid in provincial_active_pols if pol_scores.get(pid, 0) > 0]
                    if len(prov_positive) >= 2:
                        newly_earned.append("premiers-conference")
                        self._grant_achievement(session, team_id, "premiers-conference", scored_week,
                                                {"provincialsScored": prov_positive})

                # ── shadow-cabinet: 3+ opposition/parliamentary asset types active, finish top 3 ──
                if not self._already_earned(session, team_id, "shadow-cabinet"):
                    opp_types = {"opposition", "parliamentary"}
                    opp_slots = []
                    for s in active_slots:
                        pol = session.get(PoliticianModel, s.asset_id)
                        if pol and pol.asset_type in opp_types:
                            opp_slots.append(s.asset_id)
                    if len(opp_slots) >= 3:
                        # Check if this team is in the top 3 for this week
                        all_week_totals = {}
                        for t in teams:
                            total = session.scalar(
                                select(func.coalesce(func.sum(LedgerEntryModel.points), 0)).where(
                                    LedgerEntryModel.team_id == t.id,
                                    LedgerEntryModel.week == scored_week,
                                )
                            ) or 0
                            all_week_totals[t.id] = total
                        sorted_teams = sorted(all_week_totals, key=lambda k: all_week_totals[k], reverse=True)
                        rank = sorted_teams.index(team_id) + 1 if team_id in sorted_teams else 99
                        if rank <= 3:
                            newly_earned.append("shadow-cabinet")
                            self._grant_achievement(session, team_id, "shadow-cabinet", scored_week,
                                                    {"rank": rank, "oppSlots": opp_slots})

                # ── first-blood: score any points for the first time ─────────
                if not self._already_earned(session, team_id, "first-blood"):
                    # Was score 0 before and now > 0?
                    prev_total = all_time_total - week_total
                    if prev_total <= 0 < all_time_total:
                        newly_earned.append("first-blood")
                        self._grant_achievement(session, team_id, "first-blood", scored_week, {})

                # ── iron-streak-3 / iron-streak-5 ─────────────────────────────
                stats = session.scalar(
                    select(ManagerStatsModel).where(ManagerStatsModel.team_id == team_id)
                )
                if stats:
                    if stats.positive_streak >= 3 and not self._already_earned(session, team_id, "iron-streak-3"):
                        newly_earned.append("iron-streak-3")
                        self._grant_achievement(session, team_id, "iron-streak-3", scored_week,
                                                {"streak": stats.positive_streak})
                    if stats.positive_streak >= 5 and not self._already_earned(session, team_id, "iron-streak-5"):
                        newly_earned.append("iron-streak-5")
                        self._grant_achievement(session, team_id, "iron-streak-5", scored_week,
                                                {"streak": stats.positive_streak})

                # ── comeback-kid: win a week after being last place previous week ──
                if not self._already_earned(session, team_id, "comeback-kid") and scored_week > 1:
                    prev_week = scored_week - 1
                    prev_week_totals: dict[str, int] = {}
                    curr_week_totals: dict[str, int] = {}
                    for t in teams:
                        prev_week_totals[t.id] = session.scalar(
                            select(func.coalesce(func.sum(LedgerEntryModel.points), 0)).where(
                                LedgerEntryModel.team_id == t.id,
                                LedgerEntryModel.week == prev_week,
                            )
                        ) or 0
                        curr_week_totals[t.id] = session.scalar(
                            select(func.coalesce(func.sum(LedgerEntryModel.points), 0)).where(
                                LedgerEntryModel.team_id == t.id,
                                LedgerEntryModel.week == scored_week,
                            )
                        ) or 0
                    prev_sorted = sorted(prev_week_totals, key=lambda k: prev_week_totals[k])
                    curr_sorted = sorted(curr_week_totals, key=lambda k: curr_week_totals[k], reverse=True)
                    was_last = bool(prev_sorted) and prev_sorted[0] == team_id
                    is_first = bool(curr_sorted) and curr_sorted[0] == team_id
                    if was_last and is_first:
                        newly_earned.append("comeback-kid")
                        self._grant_achievement(session, team_id, "comeback-kid", scored_week, {})

                # ── full-house: all 4 active MPs score positive same week ─────
                if not self._already_earned(session, team_id, "full-house"):
                    active_scorers = [pid for pid in active_pol_ids if pol_scores.get(pid, 0) > 0]
                    if len(active_pol_ids) == ACTIVE_LINEUP_SIZE and len(active_scorers) == ACTIVE_LINEUP_SIZE:
                        newly_earned.append("full-house")
                        self._grant_achievement(session, team_id, "full-house", scored_week, {})

            session.commit()
        return newly_earned

    def get_cabinet_achievements(self, team_id: str) -> list[AchievementModel]:
        with Session(self.engine) as session:
            rows = list(session.scalars(
                select(AchievementModel)
                .where(AchievementModel.team_id == team_id)
                .order_by(AchievementModel.earned_at.desc())
            ))
            # Detach from session by converting to plain dict-backed objects
            session.expunge_all()
            return rows

    def get_cabinet_stats(self, team_id: str) -> ManagerStatsModel | None:
        with Session(self.engine) as session:
            stats = session.scalar(
                select(ManagerStatsModel).where(ManagerStatsModel.team_id == team_id)
            )
            if stats:
                session.expunge(stats)
            return stats

    def standings(self, league_id: str) -> list[tuple[TeamModel, int, ManagerStatsModel | None]]:
        with Session(self.engine) as session:
            teams = list(session.scalars(select(TeamModel).where(TeamModel.league_id == league_id)))
            totals: dict[str, int] = {team.id: 0 for team in teams}
            entries = list(session.scalars(select(LedgerEntryModel).where(LedgerEntryModel.league_id == league_id)))
            for entry in entries:
                totals[entry.team_id] = totals.get(entry.team_id, 0) + entry.points
            stats_map: dict[str, ManagerStatsModel] = {
                s.team_id: s for s in session.scalars(
                    select(ManagerStatsModel).where(ManagerStatsModel.league_id == league_id)
                )
            }
            rows = [(team, totals.get(team.id, 0), stats_map.get(team.id)) for team in teams]
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
        """Assign politicians from the DB to a new cabinet's roster slots."""
        used_asset_rows = session.execute(
            select(RosterSlotModel.asset_id)
            .join(TeamModel, TeamModel.id == RosterSlotModel.team_id)
            .where(TeamModel.league_id == league_id)
        ).all()
        used_asset_ids = {row[0] for row in used_asset_rows}

        # Prefer active politicians; fall back to all if pool is too small.
        active_pols = list(session.scalars(
            select(PoliticianModel)
            .where(PoliticianModel.status == "active")
            .order_by(PoliticianModel.role_tier.asc(), PoliticianModel.full_name.asc())
        ))
        available = [p for p in active_pols if p.id not in used_asset_ids]
        if len(available) < len(ROSTER_SLOTS):
            available = active_pols if active_pols else []

        for idx, slot_name in enumerate(ROSTER_SLOTS):
            pol = available[idx % len(available)] if available else None
            asset_id = pol.id if pol else f"placeholder-{idx}"
            default_status = "active" if idx < 4 else "bench"
            session.add(RosterSlotModel(team_id=team_id, slot=slot_name, asset_id=asset_id, lineup_status=default_status))

    def assign_mp_to_seat(self, team_id: str, slot_name: str, mp_id: str) -> RosterSlotModel:
        with Session(self.engine) as session:
            pol = session.get(PoliticianModel, mp_id)
            if pol is None:
                raise ValueError(f"Politician {mp_id!r} not found")
            if pol.status not in {"active", "pending"}:
                raise ValueError(f"Politician {pol.full_name!r} has status {pol.status!r} and cannot be assigned")
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
            league_id = team.league_id
            manager_user_id = team.manager_user_id
            session.commit()
            session.refresh(slot)
        self._add_audit_direct(
            league_id,
            manager_user_id,
            "team.mandate.updated",
            {"teamId": team_id, "slotName": slot_name, "mpId": mp_id},
        )
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

    # ── Politician queries ─────────────────────────────────────────────────────

    def create_politician(
        self,
        full_name: str,
        current_role: str = "",
        role_tier: int = 5,
        party: str = "independent",
        jurisdiction: str = "federal",
        asset_type: str = "parliamentary",
        status: str = "active",
        aliases: list[str] | None = None,
        source: str = "admin",
    ) -> PoliticianModel:
        """Manually create a politician (admin use when bootstrap sources unavailable)."""
        import re as _re  # noqa: PLC0415
        slug = _re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")
        pol_id = f"pol-{slug[:50]}"
        with Session(self.engine) as session:
            existing = session.get(PoliticianModel, pol_id)
            if existing is not None:
                return existing
            pol = PoliticianModel(
                id=pol_id,
                full_name=full_name,
                aliases_json=aliases or [],
                current_role=current_role,
                role_tier=role_tier,
                party=party,
                jurisdiction=jurisdiction,
                asset_type=asset_type,
                status=status,
                source=source,
                last_verified_at=utcnow(),
                created_at=utcnow(),
            )
            session.add(pol)
            session.commit()
            session.refresh(pol)
            return pol

    def list_politicians(self, status: str | None = None) -> list[PoliticianModel]:
        with Session(self.engine) as session:
            stmt = select(PoliticianModel).order_by(PoliticianModel.role_tier.asc(), PoliticianModel.full_name.asc())
            if status:
                stmt = stmt.where(PoliticianModel.status == status)
            return list(session.scalars(stmt))

    def get_politician(self, politician_id: str) -> PoliticianModel | None:
        with Session(self.engine) as session:
            return session.get(PoliticianModel, politician_id)

    def update_politician_role(
        self,
        politician_id: str,
        new_role: str,
        new_tier: int,
        changed_by_user_id: str,
        new_status: str | None = None,
    ) -> PoliticianModel | None:
        with Session(self.engine) as session:
            pol = session.get(PoliticianModel, politician_id)
            if pol is None:
                return None
            history = PoliticianRoleHistoryModel(
                id=f"rh-{uuid4().hex[:12]}",
                politician_id=pol.id,
                previous_role=pol.current_role,
                new_role=new_role,
                previous_tier=pol.role_tier,
                new_tier=new_tier,
                changed_at=utcnow(),
                changed_by_user_id=changed_by_user_id,
            )
            session.add(history)
            pol.current_role = new_role
            pol.role_tier = new_tier
            if new_status:
                pol.status = new_status
            pol.last_verified_at = utcnow()
            session.commit()
            session.refresh(pol)
            return pol

    def list_role_history(self, politician_id: str) -> list[PoliticianRoleHistoryModel]:
        with Session(self.engine) as session:
            stmt = (
                select(PoliticianRoleHistoryModel)
                .where(PoliticianRoleHistoryModel.politician_id == politician_id)
                .order_by(PoliticianRoleHistoryModel.changed_at.desc())
            )
            return list(session.scalars(stmt))

    # ── System config ──────────────────────────────────────────────────────────

    def get_system_config(self) -> dict:
        with Session(self.engine) as session:
            rows = list(session.scalars(select(SystemConfigModel)))
            return {row.key: row.value_json for row in rows}

    def update_system_config(self, key: str, value: object, updated_by: str = "system") -> None:
        with Session(self.engine) as session:
            row = session.get(SystemConfigModel, key)
            if row is None:
                session.add(SystemConfigModel(key=key, value_json=value, updated_by=updated_by, updated_at=utcnow()))
            else:
                row.value_json = value
                row.updated_by = updated_by
                row.updated_at = utcnow()
            session.commit()

    # ── Data sources ───────────────────────────────────────────────────────────

    def list_data_sources(self, bootstrap: bool | None = None, active: bool | None = None) -> list[DataSourceModel]:
        with Session(self.engine) as session:
            stmt = select(DataSourceModel).order_by(DataSourceModel.name.asc())
            if bootstrap is not None:
                stmt = stmt.where(DataSourceModel.bootstrap == bootstrap)
            if active is not None:
                stmt = stmt.where(DataSourceModel.active == active)
            return list(session.scalars(stmt))

    # ── Attribution ────────────────────────────────────────────────────────────

    def run_attribution(self, event_ids: list[str]) -> dict:
        """Load AI config, run AttributionEngine, return summary counts."""
        from app.api.v1.ai_client import AIClient
        from app.api.v1.attribution import AttributionEngine
        config = self.get_system_config()
        ai_client = AIClient.from_config(config) if config.get("ai_enabled") else None
        floor = float(config.get("attribution_confidence_floor", 0.65))
        with Session(self.engine) as session:
            engine = AttributionEngine(session, ai_client=ai_client, confidence_floor=floor)
            written = engine.run(event_ids)
            session.commit()
        return {"event_ids_processed": len(event_ids), "attributions_written": written}

    # ── Story clustering ────────────────────────────────────────────────────────

    def run_story_clustering(self, window_hours: int = 24) -> dict:
        """
        Run StoryClusteringEngine for unclustered articles within window_hours.
        Returns summary dict for API response.
        """
        from app.api.v1.ai_client import AIClient
        from app.api.v1.news_analysis_client import NewsAnalysisClient
        from app.api.v1.story_engine import StoryClusteringEngine
        config = self.get_system_config()
        ai_client = AIClient.from_config(config) if config.get("ai_enabled") else None
        news_client = NewsAnalysisClient(ai_client=ai_client)
        with Session(self.engine) as session:
            engine = StoryClusteringEngine(session=session, news_client=news_client)
            result = engine.process_unclustered_articles(window_hours=window_hours)
            _ = engine.check_stories_for_lifecycle_updates()
            session.commit()
        return {
            "stories_created": result.stories_created,
            "stories_updated": result.stories_updated,
            "articles_assigned": result.articles_assigned,
            "rescore_triggers": result.rescore_triggers,
        }

    def list_stories(
        self,
        status: str | None = None,
        scored: bool | None = None,
        rescore_pending: bool | None = None,
        limit: int = 100,
    ) -> list[NewsStoryModel]:
        with Session(self.engine) as session:
            stmt = (
                select(NewsStoryModel)
                .order_by(NewsStoryModel.first_seen_at.desc())
                .limit(limit)
            )
            if status is not None:
                stmt = stmt.where(NewsStoryModel.status == status)
            if scored is not None:
                stmt = stmt.where(NewsStoryModel.scored == scored)
            if rescore_pending is not None:
                stmt = stmt.where(NewsStoryModel.rescore_pending == rescore_pending)
            return list(session.scalars(stmt))

    def get_story(self, story_id: str) -> NewsStoryModel | None:
        with Session(self.engine) as session:
            return session.get(NewsStoryModel, story_id)

    def compute_bench_signals(self, team_id: str) -> list[dict]:
        """Return attribution activity for each bench (monitoring) politician in the last 24h."""
        cutoff = utcnow() - timedelta(hours=24)
        with Session(self.engine) as session:
            bench_slots = list(
                session.scalars(
                    select(RosterSlotModel).where(
                        RosterSlotModel.team_id == team_id,
                        RosterSlotModel.lineup_status == "bench",
                    )
                )
            )
            results: list[dict] = []
            for slot in bench_slots:
                pol = session.get(PoliticianModel, slot.asset_id)
                if pol is None:
                    continue
                article_count = session.scalar(
                    select(func.count(EventAttributionModel.id))
                    .join(PoliticalEventModel, PoliticalEventModel.id == EventAttributionModel.event_id)
                    .where(
                        EventAttributionModel.politician_id == pol.id,
                        PoliticalEventModel.occurred_at >= cutoff,
                    )
                ) or 0
                story_ids = list(
                    session.scalars(
                        select(PoliticalEventModel.story_id)
                        .join(EventAttributionModel, EventAttributionModel.event_id == PoliticalEventModel.id)
                        .where(
                            EventAttributionModel.politician_id == pol.id,
                            PoliticalEventModel.occurred_at >= cutoff,
                            PoliticalEventModel.story_id.isnot(None),
                        )
                        .distinct()
                    )
                )
                top_story = None
                if story_ids:
                    top_story = session.scalar(
                        select(NewsStoryModel)
                        .where(NewsStoryModel.id.in_(story_ids))
                        .order_by(NewsStoryModel.significance.desc())
                        .limit(1)
                    )
                results.append({
                    "politician_id": pol.id,
                    "politician_name": pol.full_name,
                    "article_count": article_count,
                    "top_significance": top_story.significance if top_story else 0.0,
                    "top_story_title": top_story.canonical_title if top_story else None,
                    "top_story_id": top_story.id if top_story else None,
                })
            return results

    def daily_digest(self, team_id: str) -> dict:
        """Return a single digest of today's activity for a cabinet."""
        cutoff = utcnow() - timedelta(hours=24)
        with Session(self.engine) as session:
            top_stories = list(
                session.scalars(
                    select(NewsStoryModel)
                    .where(NewsStoryModel.last_updated_at >= cutoff)
                    .order_by(NewsStoryModel.significance.desc())
                    .limit(5)
                )
            )
            slots = list(
                session.scalars(select(RosterSlotModel).where(RosterSlotModel.team_id == team_id))
            )
            active_asset_ids = [s.asset_id for s in slots if s.lineup_status == "active"]
            bench_asset_ids = [s.asset_id for s in slots if s.lineup_status == "bench"]
            total_articles_today: int = session.scalar(
                select(func.count(PoliticalEventModel.id)).where(
                    PoliticalEventModel.occurred_at >= cutoff
                )
            ) or 0
            active_mps_in_news: list[dict] = []
            for asset_id in active_asset_ids:
                pol = session.get(PoliticianModel, asset_id)
                if pol is None:
                    continue
                count: int = session.scalar(
                    select(func.count(EventAttributionModel.id))
                    .join(PoliticalEventModel, PoliticalEventModel.id == EventAttributionModel.event_id)
                    .where(
                        EventAttributionModel.politician_id == asset_id,
                        PoliticalEventModel.occurred_at >= cutoff,
                    )
                ) or 0
                if count > 0:
                    active_mps_in_news.append({
                        "politician_id": asset_id,
                        "politician_name": pol.full_name,
                        "article_count": count,
                    })
            bench_alerts: list[dict] = []
            for asset_id in bench_asset_ids:
                pol = session.get(PoliticianModel, asset_id)
                if pol is None:
                    continue
                count = session.scalar(
                    select(func.count(EventAttributionModel.id))
                    .join(PoliticalEventModel, PoliticalEventModel.id == EventAttributionModel.event_id)
                    .where(
                        EventAttributionModel.politician_id == asset_id,
                        PoliticalEventModel.occurred_at >= cutoff,
                    )
                ) or 0
                if count > 0:
                    bench_alerts.append({
                        "politician_id": asset_id,
                        "politician_name": pol.full_name,
                        "article_count": count,
                        "in_news": True,
                    })
            return {
                "top_stories": [
                    {
                        "id": s.id,
                        "canonical_title": s.canonical_title,
                        "significance": s.significance,
                        "event_type": s.event_type,
                        "jurisdiction": s.jurisdiction,
                        "article_count": s.article_count,
                    }
                    for s in top_stories
                ],
                "active_mps_in_news": active_mps_in_news,
                "bench_alerts": bench_alerts,
                "total_articles_today": total_articles_today,
            }

    def get_unscored_stories(self, week: int | None = None) -> list[NewsStoryModel]:
        """Return stories ready for initial scoring (have attributions, not yet scored)."""
        with Session(self.engine) as session:
            stmt = (
                select(NewsStoryModel)
                .where(
                    NewsStoryModel.scored.is_(False),
                    NewsStoryModel.status.in_(["active", "settling"]),
                )
                .order_by(NewsStoryModel.first_seen_at.asc())
            )
            return list(session.scalars(stmt))

    def mark_story_scored(self, story_id: str, week: int) -> None:
        with Session(self.engine) as session:
            story = session.get(NewsStoryModel, story_id)
            if story:
                story.scored = True
                story.scored_week = week
                story.last_scored_significance = story.significance
                story.rescore_pending = False
                session.commit()

    # ── Scoring ────────────────────────────────────────────────────────────────

    @staticmethod
    def _score_slot(asset_id: str, week: int) -> int:
        """Deterministic fallback weekly momentum score when no real events exist."""
        token = f"{asset_id}:{week}"
        stable = sum(ord(ch) for ch in token)
        return (stable % 9) - 2

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

    def _add_audit_direct(self, league_id: str, actor_user_id: str, action: str, metadata: dict) -> None:
        """Convenience wrapper that opens its own session for post-commit audit entries."""
        with Session(self.engine) as session:
            PersistentStore._add_audit(session, league_id, actor_user_id, action, metadata)
            session.commit()

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
