"""
ScoringEngine — independent, rule-table-driven scoring component.

Rules are loaded from ScoringRuleModel at runtime (DB-managed, no restart needed).
Scoring pipeline per active roster slot:
  1. Find the best EventAttributionModel for this politician in this event batch
  2. Look up the matching ScoringRuleModel for (event_type, asset_type)
  3. Apply attribution confidence multiplier
  4. Apply jurisdiction gate (own vs any)
  5. Optionally apply AI significance multiplier (weighted, bounded)
  6. Apply policy objective bonus if applicable
  7. Apply per-week caps from system_config
  8. Write LedgerEntryModel with attribution_id for full traceability

Called from PersistentStore.score_league_week() and POST /internal/scoring/run.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.api.v1.ai_client import AIClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ScoringResult:
    """Result for a single (team, event/story, slot) triple."""
    ledger_id: str
    team_id: str
    league_id: str
    week: int
    slot_name: str
    politician_id: str
    politician_name: str
    event_id: str
    event_title: str
    event_type: str = "general"
    base_points: int = 0
    final_points: int = 0
    attribution_type: str = "system"
    attribution_confidence: float = 1.0
    attribution_id: str = ""
    story_id: str | None = None     # set for story-based scoring
    policy_bonus: int = 0
    ai_multiplier: float = 1.0
    rule_id: str = ""


class ScoringEngine:
    """
    Loads scoring rules and system config from the database once per scoring
    cycle, then evaluates all active roster slots for all teams in a league.
    """

    def __init__(
        self,
        session: "Session",
        ai_client: AIClient,
        max_points_per_asset: int = 25,
        min_points_per_asset: int = -20,
        ai_confidence_weight: float = 0.3,
    ) -> None:
        self.session = session
        self.ai_client = ai_client
        self.max_pts = max_points_per_asset
        self.min_pts = min_points_per_asset
        self.ai_weight = ai_confidence_weight
        self._rules: dict[tuple[str, str], object] | None = None
        self._rule_id_by_key: dict[tuple[str, str], str] = {}

    def _load_rules(self, rule_version: str = "v1") -> None:
        if self._rules is not None:
            return
        from app.api.v1.persistent_store import ScoringRuleModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        rules = list(self.session.scalars(
            select(ScoringRuleModel).where(
                ScoringRuleModel.rule_version == rule_version,
                ScoringRuleModel.active.is_(True),
            )
        ))
        self._rules = {}
        for r in rules:
            key = (r.event_type, r.asset_type)
            self._rules[key] = r
            self._rule_id_by_key[key] = r.id

    def score_teams_for_events(
        self,
        league_id: str,
        week: int,
        teams: list,
        events: list,
        policy_objectives_by_team: dict[str, list],
        rule_version: str = "v1",
    ) -> list[ScoringResult]:
        """
        Core scoring loop. Returns ScoringResult objects (does NOT write to DB).
        Caller writes them after validating.
        """
        self._load_rules(rule_version)
        from app.api.v1.persistent_store import (  # noqa: PLC0415
            EventAttributionModel, PoliticianModel, RosterSlotModel,
        )
        from sqlalchemy import select  # noqa: PLC0415

        if not events:
            return []

        event_ids = [e.id for e in events]

        # Load all attributions for these events in one query
        attributions = list(self.session.scalars(
            select(EventAttributionModel).where(EventAttributionModel.event_id.in_(event_ids))
        ))
        # Index: politician_id → list[(event_id, attribution)]
        attr_by_pol: dict[str, list[tuple[str, object]]] = {}
        for attr in attributions:
            attr_by_pol.setdefault(attr.politician_id, []).append((attr.event_id, attr))

        # Load politicians for all politician_ids referenced in attributions
        pol_ids = {a.politician_id for a in attributions}
        politicians: dict[str, object] = {}
        if pol_ids:
            for p in self.session.scalars(select(PoliticianModel).where(PoliticianModel.id.in_(pol_ids))):
                politicians[p.id] = p

        # Index events by ID
        events_by_id = {e.id: e for e in events}

        # AI significance cache: (event_id) → multiplier float
        ai_sig_cache: dict[str, float] = {}

        results: list[ScoringResult] = []

        for team in teams:
            slots = list(self.session.scalars(
                select(RosterSlotModel).where(
                    RosterSlotModel.team_id == team.id,
                    RosterSlotModel.lineup_status == "active",
                )
            ))
            active_objectives: list = policy_objectives_by_team.get(team.id, [])

            for slot in slots:
                pol_id = slot.asset_id
                politician = politicians.get(pol_id)
                if politician is None:
                    continue
                if politician.status == "ineligible":
                    # Ineligibility penalty deferred — applied at next cycle only
                    continue

                pol_attrs = attr_by_pol.get(pol_id, [])
                if not pol_attrs:
                    continue

                # Pick the highest-confidence attribution for this slot
                best_attr = max(pol_attrs, key=lambda x: x[1].confidence)
                event_id, attr = best_attr
                event = events_by_id.get(event_id)
                if event is None:
                    continue

                # Jurisdiction gate
                if not self._passes_jurisdiction_gate(politician, event, slot.slot):
                    continue

                # Week modifier: whitelist and multipliers
                week_mods = self._get_week_modifiers(week)
                if week_mods:
                    whitelist = week_mods.get("event_type_whitelist")
                    if whitelist and event.event_type not in whitelist:
                        continue

                # Look up scoring rule
                rule = self._rules.get((event.event_type, politician.asset_type))
                if rule is None:
                    # Try generic "general" rule for this asset_type
                    rule = self._rules.get(("general", politician.asset_type))
                if rule is None:
                    continue

                base = rule.base_points + rule.affinity_bonus
                # Attribution confidence multiplier
                conf_mult = self._confidence_multiplier(attr.attribution_type, attr.confidence)
                points_f = base * conf_mult

                # AI significance multiplier (cached per event)
                ai_mult = 1.0
                if self.ai_client.enabled:
                    if event_id not in ai_sig_cache:
                        sig = self.ai_client.score_event_significance(
                            event_title=event.title,
                            event_type=event.event_type,
                            jurisdiction=event.jurisdiction,
                        )
                        if sig:
                            m = sig.get("multiplier", 1.0)
                            ai_sig_cache[event_id] = 1.0 + (m - 1.0) * self.ai_weight
                        else:
                            ai_sig_cache[event_id] = 1.0
                    ai_mult = ai_sig_cache[event_id]
                    points_f *= ai_mult

                # Policy objective bonus
                policy_bonus = max(
                    (obj.bonus for obj in active_objectives if event.event_type in obj.event_types),
                    default=0,
                )

                # Week modifier multipliers (event_type and asset_type)
                if week_mods:
                    event_mult = week_mods.get("multipliers", {}).get(event.event_type, 1.0)
                    asset_mult = week_mods.get("asset_multipliers", {}).get(politician.asset_type, 1.0)
                    points_f = points_f * event_mult * asset_mult

                final = int(round(points_f)) + policy_bonus
                final = max(self.min_pts, min(self.max_pts, final))

                lid = f"ledger-{uuid4().hex[:12]}"
                results.append(ScoringResult(
                    ledger_id=lid,
                    team_id=team.id,
                    league_id=league_id,
                    week=week,
                    slot_name=slot.slot,
                    politician_id=pol_id,
                    politician_name=politician.full_name,
                    event_id=event_id,
                    event_title=event.title,
                    event_type=event.event_type,
                    base_points=base,
                    final_points=final,
                    attribution_type=attr.attribution_type,
                    attribution_confidence=attr.confidence,
                    attribution_id=attr.id,
                    story_id=None,
                    policy_bonus=policy_bonus,
                    ai_multiplier=round(ai_mult, 4),
                    rule_id=rule.id,
                ))

        return results

    def score_teams_for_stories(
        self,
        league_id: str,
        week: int,
        teams: list,
        stories: list,
        policy_objectives_by_team: dict[str, list],
        story_max_points: int = 15,
        rule_version: str = "v1",
    ) -> list[ScoringResult]:
        """
        Story-based scoring loop.

        For each story, aggregates attributions across all articles in the story,
        then scores every active roster slot whose politician is attributed.
        Prevents double-scoring the same story for the same team in the same week.

        Returns ScoringResult objects (does NOT write to DB — caller persists).
        """
        self._load_rules(rule_version)
        from app.api.v1.persistent_store import (  # noqa: PLC0415
            EventAttributionModel, LedgerEntryModel, PoliticianModel,
            PoliticalEventModel, RosterSlotModel,
        )
        from sqlalchemy import func, select  # noqa: PLC0415

        if not stories:
            return []

        results: list[ScoringResult] = []

        for story in stories:
            # Get aggregated story-level attributions
            story_attributions = self._get_story_attributions(story)
            if not story_attributions:
                continue

            # Index by politician_id for O(1) lookup
            attr_by_pol = {a.politician_id: a for a in story_attributions}

            for team in teams:
                # Double-scoring guard: skip if this story already scored for this team/week
                existing_total = self.session.scalar(
                    select(func.sum(LedgerEntryModel.points)).where(
                        LedgerEntryModel.story_id == story.id,
                        LedgerEntryModel.team_id == team.id,
                        LedgerEntryModel.week == week,
                        LedgerEntryModel.league_id == league_id,
                        ~LedgerEntryModel.event.like("story.correction.%"),
                    )
                )
                if existing_total is not None:
                    # Already scored this story for this team — skip
                    continue

                active_objectives = policy_objectives_by_team.get(team.id, [])

                slots = list(self.session.scalars(
                    select(RosterSlotModel).where(
                        RosterSlotModel.team_id == team.id,
                        RosterSlotModel.lineup_status == "active",
                    )
                ))

                for slot in slots:
                    pol = self.session.get(PoliticianModel, slot.asset_id)
                    if pol is None or pol.status == "ineligible":
                        continue

                    attr = attr_by_pol.get(pol.id)
                    if attr is None:
                        continue

                    # Jurisdiction gate
                    if not self._passes_story_jurisdiction_gate(pol, story, slot.slot):
                        continue

                    # Week modifier: whitelist and multipliers
                    week_mods = self._get_week_modifiers(week)
                    if week_mods:
                        whitelist = week_mods.get("event_type_whitelist")
                        if whitelist and story.event_type not in whitelist:
                            continue

                    # Scoring rule lookup
                    rule = self._rules.get((story.event_type, pol.asset_type))
                    if rule is None:
                        rule = self._rules.get(("general", pol.asset_type))
                    if rule is None:
                        continue

                    # Significance multiplier: 5.0 is baseline "normal" story
                    sig_mult = story.significance / 5.0
                    # Follow-up discount
                    followup_disc = 0.5 if story.is_followup else 1.0
                    # Sentiment factor (asset-type aware)
                    sentiment_fact = self._sentiment_factor(story.sentiment, pol.asset_type)
                    # Attribution confidence
                    conf_mult = self._confidence_multiplier(attr.attribution_type, attr.confidence)

                    # Policy objective bonus
                    policy_bonus = max(
                        (obj.bonus for obj in active_objectives if story.event_type in obj.event_types),
                        default=0,
                    )

                    base = rule.base_points + rule.affinity_bonus
                    raw = base * sig_mult * followup_disc * sentiment_fact * conf_mult
                    # Week modifier multipliers (event_type and asset_type)
                    if week_mods:
                        event_mult = week_mods.get("multipliers", {}).get(story.event_type, 1.0)
                        asset_mult = week_mods.get("asset_multipliers", {}).get(pol.asset_type, 1.0)
                        raw = raw * event_mult * asset_mult
                    final = int(round(raw + policy_bonus * sig_mult))
                    final = max(-story_max_points, min(story_max_points, final))
                    # Also apply weekly per-asset caps
                    final = max(self.min_pts, min(self.max_pts, final))

                    lid = f"ledger-{uuid4().hex[:12]}"
                    results.append(ScoringResult(
                        ledger_id=lid,
                        team_id=team.id,
                        league_id=league_id,
                        week=week,
                        slot_name=slot.slot,
                        politician_id=pol.id,
                        politician_name=pol.full_name,
                        event_id=story.id,
                        event_title=story.canonical_title,
                        event_type=story.event_type,
                        base_points=base,
                        final_points=final,
                        attribution_type=attr.attribution_type,
                        attribution_confidence=attr.confidence,
                        attribution_id=attr.id,
                        story_id=story.id,
                        policy_bonus=policy_bonus,
                        ai_multiplier=round(sig_mult, 4),
                        rule_id=rule.id,
                    ))

        return results

    def rescore_story_corrections(
        self,
        league_id: str,
        week: int,
        teams: list,
        story: object,
        policy_objectives_by_team: dict[str, list],
        story_max_points: int = 15,
        rule_version: str = "v1",
    ) -> list[ScoringResult]:
        """
        Calculate correction ledger entries for a story whose significance changed.

        For each team that has already scored this story, calculates the delta
        between the new score and the previous total and emits a correction entry
        if |delta| >= 1 point.

        Returns a (possibly empty) list of ScoringResult objects for correction entries.
        """
        from app.api.v1.persistent_store import LedgerEntryModel  # noqa: PLC0415
        from sqlalchemy import func, select  # noqa: PLC0415

        # Get what the score would be NOW
        new_scores = self.score_teams_for_stories(
            league_id=league_id,
            week=week,
            teams=teams,
            stories=[story],
            policy_objectives_by_team=policy_objectives_by_team,
            story_max_points=story_max_points,
            rule_version=rule_version,
        )
        # score_teams_for_stories skips already-scored stories via the guard,
        # so we temporarily bypass by calling the inner loop directly.
        # Instead, compute directly by summing existing entries and diffing.

        corrections: list[ScoringResult] = []

        # Compute corrections by comparing per-team existing totals
        for team in teams:
            existing_total = self.session.scalar(
                select(func.sum(LedgerEntryModel.points)).where(
                    LedgerEntryModel.story_id == story.id,
                    LedgerEntryModel.team_id == team.id,
                    LedgerEntryModel.week == week,
                    LedgerEntryModel.league_id == league_id,
                    ~LedgerEntryModel.event.like("story.correction.%"),
                )
            )
            if existing_total is None:
                continue  # story wasn't scored for this team

            # Find what new score would be for this team/story
            team_new = next(
                (r for r in new_scores if r.team_id == team.id),
                None,
            )
            # new_scores was blocked by guard, compute directly
            if team_new is None:
                new_total = self._calc_story_score_for_team(
                    league_id=league_id,
                    week=week,
                    team=team,
                    story=story,
                    policy_objectives=policy_objectives_by_team.get(team.id, []),
                    story_max_points=story_max_points,
                    rule_version=rule_version,
                )
            else:
                new_total = team_new.final_points

            delta = new_total - (existing_total or 0)
            if abs(delta) < 1:
                continue

            # Find attribution info for ledger traceability
            story_attrs = self._get_story_attributions(story)
            best_attr = story_attrs[0] if story_attrs else None

            lid = f"ledger-{uuid4().hex[:12]}"
            corrections.append(ScoringResult(
                ledger_id=lid,
                team_id=team.id,
                league_id=league_id,
                week=week,
                slot_name="",
                politician_id=best_attr.politician_id if best_attr else "",
                politician_name="",
                event_id=story.id,
                event_title=f"[CORRECTION] {story.canonical_title}",
                event_type=story.event_type,
                base_points=delta,
                final_points=delta,
                attribution_type=best_attr.attribution_type if best_attr else "system",
                attribution_confidence=best_attr.confidence if best_attr else 1.0,
                attribution_id=best_attr.id if best_attr else "",
                story_id=story.id,
                policy_bonus=0,
                ai_multiplier=round(story.significance / 5.0, 4),
                rule_id=f"correction.v{story.score_version + 1}",
            ))

        return corrections

    def _calc_story_score_for_team(
        self,
        league_id: str,
        week: int,
        team: object,
        story: object,
        policy_objectives: list,
        story_max_points: int,
        rule_version: str,
    ) -> int:
        """Calculate the score a team would receive for a story right now."""
        self._load_rules(rule_version)
        from app.api.v1.persistent_store import PoliticianModel, RosterSlotModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        story_attrs = self._get_story_attributions(story)
        attr_by_pol = {a.politician_id: a for a in story_attrs}
        total = 0

        slots = list(self.session.scalars(
            select(RosterSlotModel).where(
                RosterSlotModel.team_id == team.id,
                RosterSlotModel.lineup_status == "active",
            )
        ))
        for slot in slots:
            pol = self.session.get(PoliticianModel, slot.asset_id)
            if pol is None or pol.status == "ineligible":
                continue
            attr = attr_by_pol.get(pol.id)
            if attr is None:
                continue
            if not self._passes_story_jurisdiction_gate(pol, story, slot.slot):
                continue
            rule = self._rules.get((story.event_type, pol.asset_type)) or self._rules.get(("general", pol.asset_type))
            if rule is None:
                continue
            sig_mult = story.significance / 5.0
            followup = 0.5 if story.is_followup else 1.0
            sentiment = self._sentiment_factor(story.sentiment, pol.asset_type)
            conf = self._confidence_multiplier(attr.attribution_type, attr.confidence)
            policy_bonus = max(
                (obj.bonus for obj in policy_objectives if story.event_type in obj.event_types),
                default=0,
            )
            base = rule.base_points + rule.affinity_bonus
            raw = base * sig_mult * followup * sentiment * conf
            final = int(round(raw + policy_bonus * sig_mult))
            final = max(-story_max_points, min(story_max_points, final))
            final = max(self.min_pts, min(self.max_pts, final))
            total += final
        return total

    def _get_story_attributions(self, story: object) -> list:
        """
        Aggregate article-level attributions for a story.

        Collects all EventAttributionModel rows for articles linked to this story,
        groups by politician_id, and returns the highest-confidence attribution
        per politician.
        """
        from app.api.v1.persistent_store import EventAttributionModel, PoliticalEventModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        article_ids = list(self.session.scalars(
            select(PoliticalEventModel.id).where(PoliticalEventModel.story_id == story.id)
        ))
        if not article_ids:
            return []

        all_attrs = list(self.session.scalars(
            select(EventAttributionModel)
            .where(EventAttributionModel.event_id.in_(article_ids))
            .order_by(EventAttributionModel.confidence.desc())
        ))

        # Deduplicate: keep highest-confidence attribution per politician
        seen: dict[str, object] = {}
        for attr in all_attrs:
            if attr.politician_id not in seen:
                seen[attr.politician_id] = attr
        return list(seen.values())

    def score_ineligibility_penalties(
        self,
        league_id: str,
        week: int,
        teams: list,
        penalty_points: int = -3,
    ) -> list[ScoringResult]:
        """
        Emit penalty ledger entries for any active slot holding an ineligible
        politician. This is the deferred ineligibility penalty (applied at the
        start of the next cycle, not mid-week).
        """
        from app.api.v1.persistent_store import PoliticianModel, RosterSlotModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        results: list[ScoringResult] = []
        for team in teams:
            slots = list(self.session.scalars(
                select(RosterSlotModel).where(
                    RosterSlotModel.team_id == team.id,
                    RosterSlotModel.lineup_status == "active",
                )
            ))
            for slot in slots:
                pol = self.session.get(PoliticianModel, slot.asset_id)
                if pol is None or pol.status != "ineligible":
                    continue
                lid = f"ledger-{uuid4().hex[:12]}"
                results.append(ScoringResult(
                    ledger_id=lid,
                    team_id=team.id,
                    league_id=league_id,
                    week=week,
                    slot_name=slot.slot,
                    politician_id=pol.id,
                    politician_name=pol.full_name,
                    event_id="",
                    event_title=f"Ineligibility penalty: {pol.full_name}",
                    base_points=penalty_points,
                    final_points=penalty_points,
                    attribution_type="system",
                    attribution_confidence=1.0,
                    attribution_id="",
                    policy_bonus=0,
                    ai_multiplier=1.0,
                    rule_id="ineligibility-penalty",
                ))
        return results

    # ── internal ─────────────────────────────────────────────────────────────

    def _get_week_modifiers(self, week: int) -> dict | None:
        """
        Load week_modifiers from system_config and return the entry for the given
        week number (if one exists). Returns None if no modifier is configured for
        this week.
        """
        from app.api.v1.persistent_store import SystemConfigModel  # noqa: PLC0415

        cfg = self.session.get(SystemConfigModel, "week_modifiers")
        if cfg is None:
            return None
        mods = cfg.value_json
        if not isinstance(mods, dict):
            return None
        return mods.get(str(week))

    @staticmethod
    def _confidence_multiplier(attribution_type: str, confidence: float) -> float:
        """
        Map attribution type → base multiplier, then blend with actual confidence.
        direct_name → 1.00, alias → 0.95, role_title → 0.60
        """
        type_mult = {"direct_name": 1.00, "alias": 0.95, "role_title": 0.60}.get(attribution_type, 0.60)
        return type_mult * min(confidence / 0.95, 1.0)

    @staticmethod
    def _passes_jurisdiction_gate(politician, event, slot_name: str) -> bool:
        """
        Jurisdiction gate:
        - jurisdiction_scope "any" always passes (intergovernmental, leadership_change, general)
        - jurisdiction_scope "own": politician's jurisdiction must match event's jurisdiction,
          OR the event is intergovernmental (which crosses jurisdictions by definition).
        """
        p_jur = (politician.jurisdiction or "federal").upper()
        e_jur = (event.jurisdiction or "federal").upper()
        if event.event_type in {"intergovernmental", "leadership_change", "general"}:
            return True
        if p_jur == "FEDERAL":
            return e_jur in {"FEDERAL", "CANADA"}
        return p_jur == e_jur

    @staticmethod
    def _passes_story_jurisdiction_gate(politician, story, slot_name: str) -> bool:
        """Same gate logic, applied to a NewsStoryModel instead of PoliticalEventModel."""
        p_jur = (politician.jurisdiction or "federal").upper()
        s_jur = (story.jurisdiction or "federal").upper()
        if story.event_type in {"intergovernmental", "leadership_change", "general"}:
            return True
        if p_jur == "FEDERAL":
            return s_jur in {"FEDERAL", "CANADA"}
        return p_jur == s_jur

    @staticmethod
    def _sentiment_factor(sentiment: float, asset_type: str) -> float:
        """
        How does story sentiment affect scoring for this asset_type?

        Governing (executive/cabinet):
          positive news → bonus (up to 1.25×), negative news → penalty (down to 0.5×)
        Opposition:
          negative-for-government news → bonus, positive → slight reduction
        Parliamentary:
          minimal sentiment effect (0.80× – 1.00×)
        """
        s = max(-1.0, min(1.0, sentiment))
        if asset_type in {"executive", "cabinet"}:
            # Linear: sentiment 1.0 → 1.25×, sentiment -1.0 → 0.50×
            return max(0.5, 0.875 + s * 0.375)
        elif asset_type == "opposition":
            # Inverted: good-for-govt news is bad for opposition
            return max(0.5, 0.875 + (-s) * 0.375)
        else:
            # Parliamentary: small effect
            return max(0.8, 0.9 + s * 0.1)
