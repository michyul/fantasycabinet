"""
StoryClusteringEngine — groups raw political event articles into canonical
NewsStory records, manages story lifecycle, and flags stories for re-scoring.

Pipeline (called from worker after every ingest + attribution cycle):

  1. process_unclustered_articles()
       - Loads PoliticalEventModel rows with story_id IS NULL
       - Calls NewsAnalysisClient.cluster_articles() (AI or Jaccard fallback)
       - Upserts NewsStoryModel, links events via story_id FK
       - For new articles landing in an EXISTING story: checks if significance
         changed enough to set rescore_pending = True

  2. check_stories_for_lifecycle_updates()
       - Moves active → settling → archived based on age
       - Does NOT delete rows (archived stories are kept for audit)

  3. get_stories_needing_rescore()
       - Returns stories where rescore_pending=True and rescore_count < 3

Results from (1) are returned as a ClusteringResult dataclass for worker logging.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.api.v1.news_analysis_client import ClusterProposal, NewsAnalysisClient

log = logging.getLogger(__name__)

# ── Lifecycle constants ────────────────────────────────────────────────────────
_CLUSTER_WINDOW_HOURS = 24          # look back this far for unclustered articles
_ACTIVE_STORY_HOURS = 24            # articles arrive freely
_SETTLING_STORY_HOURS = 48          # new articles still cluster in; higher rescore bar
_ARCHIVE_STORY_HOURS = 72           # story is frozen
_MAX_RESCORES = 3                   # hard limit on correction cycles per story
_BATCH_SIZE = 25                    # max articles per AI clustering call
_SETTLING_RESCORE_THRESHOLD = 2.5   # higher bar when story is settling
_ACTIVE_RESCORE_THRESHOLD = 1.5     # default threshold for active stories
_STORY_MATCH_THRESHOLD = 0.45       # Jaccard threshold for matching new cluster to existing story


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ClusteringResult:
    """Summary statistics returned after a clustering pass."""
    stories_created: int = 0
    stories_updated: int = 0
    articles_assigned: int = 0
    rescore_triggers: int = 0
    articles_skipped: int = 0        # articles older than window or already assigned


class StoryClusteringEngine:
    """
    Groups raw PoliticalEventModel rows into NewsStoryModel entities and
    manages story lifecycle transitions.
    """

    def __init__(
        self,
        session: "Session",
        news_client: NewsAnalysisClient | None = None,
    ) -> None:
        self._session = session
        self._client = news_client if news_client is not None else NewsAnalysisClient()

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_unclustered_articles(
        self, window_hours: int = _CLUSTER_WINDOW_HOURS
    ) -> ClusteringResult:
        """
        Main entry point for each worker cycle.

        Loads all PoliticalEventModel rows with story_id IS NULL within the
        time window, clusters them, and upserts NewsStoryModel records.
        Returns statistics for worker logging.
        """
        from app.api.v1.persistent_store import NewsStoryModel, PoliticalEventModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        result = ClusteringResult()
        cutoff = _utcnow() - timedelta(hours=window_hours)

        unclustered = list(
            self._session.scalars(
                select(PoliticalEventModel)
                .where(
                    PoliticalEventModel.story_id.is_(None),
                    PoliticalEventModel.created_at >= cutoff,
                )
                .order_by(PoliticalEventModel.created_at.asc())
                .limit(_BATCH_SIZE)
            )
        )

        if not unclustered:
            log.debug("story_engine: no unclustered articles in %d-hour window", window_hours)
            return result

        # Load existing active/settling stories for potential merging
        story_cutoff = _utcnow() - timedelta(hours=_SETTLING_STORY_HOURS)
        existing_stories: list[NewsStoryModel] = list(
            self._session.scalars(
                select(NewsStoryModel).where(
                    NewsStoryModel.status.in_(["active", "settling"]),
                    NewsStoryModel.last_updated_at >= story_cutoff,
                )
            )
        )

        # Build article dicts for the AI/heuristic client
        article_dicts: list[dict] = [
            {
                "id": a.id,
                "title": a.title or "",
                "summary": (a.payload_json or {}).get("summary", "")[:300],
                "event_type": a.event_type or "general",
                "jurisdiction": a.jurisdiction or "federal",
            }
            for a in unclustered
        ]

        # Cluster
        clusters = self._client.cluster_articles(article_dicts)
        log.info(
            "story_engine: clustered %d articles into %d stories",
            len(unclustered),
            len(clusters),
        )

        # Upsert stories and link articles
        for cluster in clusters:
            existing = self._find_matching_story(cluster, existing_stories)
            if existing is not None:
                self._merge_into_story(existing, cluster, unclustered, result)
            else:
                new_story = self._create_story(cluster, unclustered)
                self._session.add(new_story)
                self._session.flush()   # get the PK before linking
                existing_stories.append(new_story)
                self._link_articles(new_story, cluster, unclustered, result)
                result.stories_created += 1

        return result

    def check_stories_for_lifecycle_updates(self) -> int:
        """
        Advance stories through their lifecycle stages:
          active  → settling  (after _ACTIVE_STORY_HOURS)
          settling → archived (after _SETTLING_STORY_HOURS)

        Returns count of stories whose status changed.
        """
        from app.api.v1.persistent_store import NewsStoryModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        now = _utcnow()
        settling_cutoff = now - timedelta(hours=_ACTIVE_STORY_HOURS)
        archive_cutoff = now - timedelta(hours=_SETTLING_STORY_HOURS)
        updated = 0

        stories = list(
            self._session.scalars(
                select(NewsStoryModel).where(NewsStoryModel.status.in_(["active", "settling"]))
            )
        )
        for story in stories:
            if story.last_updated_at <= archive_cutoff and story.status != "archived":
                story.status = "archived"
                updated += 1
            elif story.last_updated_at <= settling_cutoff and story.status == "active":
                story.status = "settling"
                updated += 1

        if updated:
            log.info("story_engine: advanced lifecycle for %d stories", updated)
        return updated

    def get_stories_needing_rescore(self) -> list:
        """
        Return NewsStoryModel objects flagged for re-scoring.
        The caller (ScoringEngine / persistent_store) processes these.
        """
        from app.api.v1.persistent_store import NewsStoryModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        return list(
            self._session.scalars(
                select(NewsStoryModel).where(
                    NewsStoryModel.scored.is_(True),
                    NewsStoryModel.rescore_pending.is_(True),
                    NewsStoryModel.rescore_count < _MAX_RESCORES,
                )
            )
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _find_matching_story(
        self,
        cluster: ClusterProposal,
        existing_stories: list,
    ) -> object | None:
        """
        Find an existing story whose canonical_title is similar enough to the
        new cluster's title to be considered the same story.
        """
        cluster_tokens = NewsAnalysisClient.normalise(cluster.canonical_title)
        best_score = 0.0
        best_story = None
        for story in existing_stories:
            story_tokens = NewsAnalysisClient.normalise(story.canonical_title)
            score = NewsAnalysisClient.jaccard(cluster_tokens, story_tokens)
            if score > best_score and score >= _STORY_MATCH_THRESHOLD:
                best_score = score
                best_story = story
        return best_story

    def _create_story(
        self,
        cluster: ClusterProposal,
        unclustered: list,
    ) -> object:
        """Create a new NewsStoryModel for a cluster."""
        from app.api.v1.persistent_store import NewsStoryModel  # noqa: PLC0415

        # Deterministic ID from canonical title (stable across runs)
        story_id = "story-" + hashlib.sha1(
            cluster.canonical_title.encode("utf-8")
        ).hexdigest()[:16]

        now = _utcnow()
        return NewsStoryModel(
            id=story_id,
            canonical_title=cluster.canonical_title,
            canonical_summary=cluster.canonical_summary,
            event_type=cluster.event_type,
            jurisdiction=cluster.jurisdiction,
            significance=cluster.significance,
            sentiment=cluster.sentiment,
            is_followup=cluster.is_followup,
            article_count=len(cluster.article_indices),
            status="active",
            scored=False,
            scored_week=None,
            last_scored_significance=None,
            score_version=0,
            rescore_count=0,
            rescore_pending=False,
            first_seen_at=now,
            last_updated_at=now,
        )

    def _merge_into_story(
        self,
        story: object,
        cluster: ClusterProposal,
        unclustered: list,
        result: ClusteringResult,
    ) -> None:
        """
        Add new articles to an existing story and optionally flag for re-score.
        """
        new_titles = [
            unclustered[i].title
            for i in cluster.article_indices
            if i < len(unclustered)
        ]
        new_summaries = [
            (unclustered[i].payload_json or {}).get("summary", "")
            for i in cluster.article_indices
            if i < len(unclustered)
        ]

        # Ask AI if significance changed (best-effort, falls back to no-change)
        assessment = self._client.assess_story_update(
            story_title=story.canonical_title,
            story_event_type=story.event_type,
            current_significance=story.significance,
            current_sentiment=story.sentiment,
            article_count=story.article_count,
            new_article_titles=new_titles,
            new_article_summaries=new_summaries,
        )

        story.significance = assessment.updated_significance
        story.sentiment = assessment.updated_sentiment
        story.article_count += len(cluster.article_indices)
        story.last_updated_at = _utcnow()

        # Determine rescore threshold based on lifecycle stage
        threshold = (
            _SETTLING_RESCORE_THRESHOLD
            if story.status == "settling"
            else _ACTIVE_RESCORE_THRESHOLD
        )
        if (
            assessment.should_rescore
            and story.scored
            and story.rescore_count < _MAX_RESCORES
            and abs(assessment.significance_delta) >= threshold
        ):
            story.rescore_pending = True
            result.rescore_triggers += 1
            log.info(
                "story_engine: rescore flagged story=%s delta=%.1f reason=%s",
                story.id,
                assessment.significance_delta,
                assessment.reason[:80],
            )

        self._link_articles(story, cluster, unclustered, result)
        result.stories_updated += 1

    def _link_articles(
        self,
        story: object,
        cluster: ClusterProposal,
        unclustered: list,
        result: ClusteringResult,
    ) -> None:
        """Set story_id on each article in the cluster."""
        for idx in cluster.article_indices:
            if idx < len(unclustered):
                unclustered[idx].story_id = story.id
                result.articles_assigned += 1
