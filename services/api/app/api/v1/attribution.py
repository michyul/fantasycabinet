"""
AttributionEngine — links ingested political events to specific politicians.

For each event, scans title + summary against every active politician's:
  - full_name tokens  (direct_name, confidence 0.95)
  - aliases_json      (alias,       confidence 0.90)
  - current_role      (role_title,  confidence 0.65)

Writes EventAttributionModel rows for matches at or above the configured
confidence floor (default 0.65). Optionally augments with Ollama AI.

Called via POST /api/v1/internal/attribution/run with a list of event IDs.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.api.v1.ai_client import AIClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _name_tokens(full_name: str) -> list[str]:
    """
    Extract meaningful tokens from a name for matching.
    Filters out common particles (de, le, la, du, van, von, bin, …) and
    tokens shorter than 3 chars to reduce false-positive matches.
    """
    _PARTICLES = {"de", "le", "la", "du", "des", "les", "van", "von", "bin", "al", "el", "di", "da"}
    tokens = re.split(r"[\s\-']+", full_name.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _PARTICLES]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class AttributionEngine:
    """
    Scans a batch of events against the active politician roster and writes
    EventAttributionModel rows. Idempotent: skips already-attributed events.
    """

    def __init__(self, session: "Session", ai_client: AIClient, confidence_floor: float = 0.65) -> None:
        self.session = session
        self.ai_client = ai_client
        self.confidence_floor = confidence_floor

    def run(self, event_ids: list[str]) -> int:
        """
        Attribute a batch of events by their IDs.
        Returns number of attribution rows written.
        """
        from app.api.v1.persistent_store import EventAttributionModel, PoliticianModel, PoliticalEventModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        if not event_ids:
            return 0

        # Load events
        events = list(self.session.scalars(
            select(PoliticalEventModel).where(PoliticalEventModel.id.in_(event_ids))
        ))
        if not events:
            return 0

        # Load all active politicians once
        politicians = list(self.session.scalars(
            select(PoliticianModel).where(PoliticianModel.status == "active")
        ))
        if not politicians:
            return 0

        # Pre-compute token sets for each politician (done once per batch)
        pol_tokens: dict[str, dict] = {}
        for p in politicians:
            aliases: list[str] = p.aliases_json or []
            pol_tokens[p.id] = {
                "name_tokens": _name_tokens(p.full_name),
                "alias_phrases": [_normalise(a) for a in aliases],
                "role_tokens":   _name_tokens(p.current_role),
            }

        # Check which (event_id, politician_id) pairs already have attributions
        existing_pairs: set[tuple[str, str]] = set()
        existing = list(self.session.scalars(
            select(EventAttributionModel).where(EventAttributionModel.event_id.in_(event_ids))
        ))
        for row in existing:
            existing_pairs.add((row.event_id, row.politician_id))

        written = 0
        for event in events:
            event_text = _normalise(f"{event.title} {event.payload_json.get('summary', '')}")
            event_summary = str(event.payload_json.get("summary", ""))[:400]

            for politician in politicians:
                if (event.id, politician.id) in existing_pairs:
                    continue

                best = self._best_match(event_text, politician, pol_tokens[politician.id])
                if best is None:
                    continue

                attribution_type, confidence, matched_text = best

                # Optional AI augmentation — can raise/lower confidence
                if self.ai_client.enabled:
                    ai_conf = self.ai_client.score_attribution_confidence(
                        event_title=event.title,
                        event_summary=event_summary,
                        politician_name=politician.full_name,
                        politician_role=politician.current_role,
                    )
                    if ai_conf is not None:
                        # Blend: weighted average, AI contributes 30% by default
                        weight = 0.3
                        confidence = confidence * (1 - weight) + ai_conf * weight

                if confidence < self.confidence_floor:
                    continue

                self.session.add(EventAttributionModel(
                    id=f"attr-{uuid4().hex[:12]}",
                    event_id=event.id,
                    politician_id=politician.id,
                    attribution_type=attribution_type,
                    confidence=round(confidence, 4),
                    matched_text=matched_text[:500],
                    created_at=_utcnow(),
                ))
                written += 1

        return written

    # ── internal ─────────────────────────────────────────────────────────────

    def _best_match(
        self,
        event_text: str,
        politician,
        tokens: dict,
    ) -> tuple[str, float, str] | None:
        """
        Return (attribution_type, confidence, matched_text) for the highest-
        confidence match found, or None if no match reaches threshold 0.60
        (slightly below floor to allow AI augmentation to push it over).
        """
        best_conf = 0.0
        best_type = "role_title"
        best_matched = ""

        # 1. Direct name match — all significant name tokens must appear
        name_tokens = tokens["name_tokens"]
        if name_tokens:
            matches = [t for t in name_tokens if t in event_text]
            coverage = len(matches) / len(name_tokens)
            if coverage >= 0.8:  # ≥80% of name tokens present
                conf = 0.95 * coverage
                if conf > best_conf:
                    best_conf = conf
                    best_type = "direct_name"
                    best_matched = " ".join(matches)

        # 2. Alias match — any full alias phrase present verbatim
        for alias_phrase in tokens["alias_phrases"]:
            if alias_phrase and alias_phrase in event_text:
                if 0.90 > best_conf:
                    best_conf = 0.90
                    best_type = "alias"
                    best_matched = alias_phrase

        # 3. Role title match — majority of role tokens present
        role_tokens = tokens["role_tokens"]
        if role_tokens and best_conf < 0.65:
            matches = [t for t in role_tokens if t in event_text]
            coverage = len(matches) / len(role_tokens)
            if coverage >= 0.75:
                conf = 0.65 * coverage
                if conf > best_conf:
                    best_conf = conf
                    best_type = "role_title"
                    best_matched = " ".join(matches)

        if best_conf < 0.60:
            return None
        return best_type, best_conf, best_matched
