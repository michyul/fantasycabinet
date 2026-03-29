"""
NewsAnalysisClient — structured AI calls for political news analysis.

Uses Ollama's format:json mode for schema-constrained responses.
Falls back to a deterministic Jaccard-similarity heuristic when AI is
unavailable or disabled — so clustering ALWAYS produces results.

Two call types:
  cluster_articles()      — group raw articles into canonical news stories
  assess_story_update()   — determine whether a story's significance changed
                             enough to trigger re-scoring
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.api.v1.ai_client import AIClient

log = logging.getLogger(__name__)

# ── Significance defaults for AI-unavailable fallback ─────────────────────────
_DEFAULT_SIGNIFICANCE: dict[str, float] = {
    "confidence": 8.0,
    "ethics": 6.5,
    "election": 6.0,
    "intergovernmental": 5.5,
    "legislative": 5.5,
    "executive": 5.0,
    "policy": 4.5,
    "opposition": 4.0,
    "general": 3.0,
    "leadership_change": 7.0,
}

_JACCARD_THRESHOLD = 0.45   # min title-token overlap to cluster two articles
_RESCORE_DELTA_THRESHOLD = 1.5  # min significance change to trigger re-score

# Common English/French stop-words removed before Jaccard comparison
_STOP: frozenset[str] = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would could should may might shall of in on at for to from "
    "with by as and or not no but its it s de la le les du des un une "
    "pour par sur est avec dans que qui ne se canadian canada".split()
)


# ── Typed result objects ───────────────────────────────────────────────────────

@dataclass
class ClusterProposal:
    """One proposed canonical news story, produced by clustering."""
    canonical_title: str
    event_type: str = "general"
    jurisdiction: str = "federal"
    significance: float = 5.0          # 1–10
    sentiment: float = 0.0             # −1 to +1
    is_followup: bool = False
    article_indices: list[int] = field(default_factory=list)
    canonical_summary: str = ""


@dataclass
class RescoreAssessment:
    """Result of evaluating whether a developing story needs re-scoring."""
    updated_significance: float
    updated_sentiment: float
    significance_delta: float
    should_rescore: bool
    reason: str = ""


# ── Main client ───────────────────────────────────────────────────────────────

class NewsAnalysisClient:
    """
    Thin facade over AIClient that issues structured news-analysis prompts.

    All public methods return sensible fallback values on any error — AI is
    best-effort. Callers must not assume AI availability.
    """

    MAX_ARTICLES_PER_CALL = 25   # Ollama context window guard

    def __init__(self, ai_client: "AIClient | None" = None) -> None:
        self._ai = ai_client

    # ── Public API ────────────────────────────────────────────────────────────

    def cluster_articles(
        self,
        articles: list[dict],   # {"id", "title", "summary", "event_type", "jurisdiction"}
    ) -> list[ClusterProposal]:
        """
        Group raw news articles into distinct political news stories.

        Tries AI clustering first; falls back to Jaccard title similarity.
        Returns at least one ClusterProposal per input article (no articles dropped).
        """
        if not articles:
            return []
        batch = articles[: self.MAX_ARTICLES_PER_CALL]

        if self._ai_enabled():
            result = self._ai_cluster(batch)
            if result is not None:
                return result

        return self._heuristic_cluster(batch)

    def assess_story_update(
        self,
        story_title: str,
        story_event_type: str,
        current_significance: float,
        current_sentiment: float,
        article_count: int,
        new_article_titles: list[str],
        new_article_summaries: list[str],
    ) -> RescoreAssessment:
        """
        Determine whether a developing story's significance has changed enough
        to warrant re-scoring existing ledger entries.

        Falls back to "no change, no rescore" when AI is unavailable.
        """
        if self._ai_enabled():
            result = self._ai_assess_update(
                story_title,
                story_event_type,
                current_significance,
                current_sentiment,
                article_count,
                new_article_titles,
                new_article_summaries,
            )
            if result is not None:
                return result

        return RescoreAssessment(
            updated_significance=current_significance,
            updated_sentiment=current_sentiment,
            significance_delta=0.0,
            should_rescore=False,
            reason="AI unavailable — no re-score assessment",
        )

    # ── AI calls ──────────────────────────────────────────────────────────────

    def _ai_enabled(self) -> bool:
        return self._ai is not None and getattr(self._ai, "enabled", False)

    def _ai_cluster(self, articles: list[dict]) -> list[ClusterProposal] | None:
        assert self._ai is not None
        numbered = "\n".join(
            f"[{i}] Title: {a['title'][:120]}\n    Summary: {a.get('summary', '')[:200]}"
            for i, a in enumerate(articles)
        )
        prompt = (
            "You are a Canadian political news analyst. "
            "Group the following news articles into distinct political news stories.\n\n"
            f"ARTICLES:\n{numbered}\n\n"
            "Return ONLY a JSON object with this exact schema (no other text):\n"
            '{"clusters":['
            '{"canonical_title":"string",'
            '"event_type":"general|legislative|executive|policy|opposition|election|intergovernmental|ethics|confidence|leadership_change",'
            '"jurisdiction":"federal|ON|QC|BC|AB|SK|MB|NS|NB|NL|PE",'
            '"significance":6.5,'
            '"sentiment":0.0,'
            '"is_followup":false,'
            '"indices":[0,1]}'
            "]}\n\n"
            "Rules:\n"
            "- significance: 1=trivial, 5=routine political news, 10=historic constitutional crisis\n"
            "- sentiment: -1=very bad for the current governing party, 0=neutral, 1=very positive\n"
            "- is_followup: true if this continues an ongoing story from the previous 24 hours\n"
            "- Every article index must appear in exactly one cluster\n"
            "- Use the fewest clusters that correctly separates distinct stories\n"
            "Return valid JSON only."
        )
        try:
            data = self._ai.generate_structured(prompt)
            if not data or "clusters" not in data:
                return None
            return self._parse_cluster_response(data["clusters"], articles)
        except Exception as exc:  # noqa: BLE001
            log.warning("NewsAnalysisClient._ai_cluster failed: %s", exc)
            return None

    def _ai_assess_update(
        self,
        story_title: str,
        event_type: str,
        current_significance: float,
        current_sentiment: float,
        article_count: int,
        new_titles: list[str],
        new_summaries: list[str],
    ) -> RescoreAssessment | None:
        assert self._ai is not None
        new_text = "\n".join(
            f"[{i}] {t}\n    {s[:200]}"
            for i, (t, s) in enumerate(zip(new_titles, new_summaries))
        )
        prompt = (
            "You are a Canadian political news analyst evaluating a developing story.\n\n"
            f'EXISTING STORY: "{story_title}"\n'
            f"Type: {event_type} | Current significance: {current_significance}/10 | "
            f"Current sentiment: {current_sentiment:.1f} | Article count so far: {article_count}\n\n"
            f"NEW ARTICLES:\n{new_text}\n\n"
            "Has this story evolved materially since the initial coverage?\n"
            "Return ONLY this JSON (no other text):\n"
            '{"updated_significance":6.5,"updated_sentiment":0.0,"significance_delta":0.0,'
            '"should_rescore":false,"reason":"string"}\n\n'
            f"Set should_rescore=true only if |significance_delta| >= {_RESCORE_DELTA_THRESHOLD}.\n"
            "Return valid JSON only."
        )
        try:
            data = self._ai.generate_structured(prompt)
            if not data:
                return None
            return RescoreAssessment(
                updated_significance=float(
                    max(1.0, min(10.0, data.get("updated_significance", current_significance)))
                ),
                updated_sentiment=float(
                    max(-1.0, min(1.0, data.get("updated_sentiment", current_sentiment)))
                ),
                significance_delta=float(data.get("significance_delta", 0.0)),
                should_rescore=bool(data.get("should_rescore", False)),
                reason=str(data.get("reason", ""))[:500],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("NewsAnalysisClient._ai_assess_update failed: %s", exc)
            return None

    def _parse_cluster_response(
        self,
        raw_clusters: list[dict],
        articles: list[dict],
    ) -> list[ClusterProposal] | None:
        """Parse and validate Ollama's cluster JSON, ensure all indices covered."""
        if not raw_clusters:
            return None

        result: list[ClusterProposal] = []
        covered: set[int] = set()

        for c in raw_clusters:
            raw_indices = c.get("indices", [])
            indices = [int(i) for i in raw_indices if 0 <= int(i) < len(articles)]
            if not indices:
                continue
            covered.update(indices)
            summaries = " ".join(
                articles[i].get("summary", "")[:300] for i in indices
            )
            result.append(
                ClusterProposal(
                    canonical_title=str(c.get("canonical_title", articles[indices[0]]["title"]))[:300],
                    event_type=str(c.get("event_type", "general")),
                    jurisdiction=str(c.get("jurisdiction", "federal")),
                    significance=float(max(1.0, min(10.0, c.get("significance", 5.0)))),
                    sentiment=float(max(-1.0, min(1.0, c.get("sentiment", 0.0)))),
                    is_followup=bool(c.get("is_followup", False)),
                    article_indices=indices,
                    canonical_summary=summaries[:500],
                )
            )

        # Ensure no articles were dropped — add singletons for any uncovered index
        for i, article in enumerate(articles):
            if i not in covered:
                result.append(
                    ClusterProposal(
                        canonical_title=article["title"][:300],
                        event_type=article.get("event_type", "general"),
                        jurisdiction=article.get("jurisdiction", "federal"),
                        significance=_DEFAULT_SIGNIFICANCE.get(
                            article.get("event_type", "general"), 3.0
                        ),
                        sentiment=0.0,
                        is_followup=False,
                        article_indices=[i],
                        canonical_summary=article.get("summary", "")[:500],
                    )
                )

        return result if result else None

    # ── Heuristic fallback ────────────────────────────────────────────────────

    def _heuristic_cluster(self, articles: list[dict]) -> list[ClusterProposal]:
        """
        Group articles by Jaccard similarity of normalised title tokens.
        O(n²) but n ≤ 25 so performance is fine.
        """
        normalised = [NewsAnalysisClient.normalise(a["title"]) for a in articles]
        assigned = [False] * len(articles)
        clusters: list[list[int]] = []

        for i in range(len(articles)):
            if assigned[i]:
                continue
            group = [i]
            assigned[i] = True
            for j in range(i + 1, len(articles)):
                if not assigned[j] and NewsAnalysisClient.jaccard(normalised[i], normalised[j]) >= _JACCARD_THRESHOLD:
                    group.append(j)
                    assigned[j] = True
            clusters.append(group)

        return [self._group_to_proposal(articles, indices) for indices in clusters]

    def _group_to_proposal(self, articles: list[dict], indices: list[int]) -> ClusterProposal:
        rep = articles[indices[0]]
        canonical_title = max(
            (articles[i]["title"] for i in indices), key=len
        )
        summaries = " ".join(articles[i].get("summary", "")[:300] for i in indices)
        et = rep.get("event_type", "general")
        return ClusterProposal(
            canonical_title=canonical_title[:300],
            event_type=et,
            jurisdiction=rep.get("jurisdiction", "federal"),
            significance=_DEFAULT_SIGNIFICANCE.get(et, 4.0),
            sentiment=0.0,
            is_followup=False,
            article_indices=indices,
            canonical_summary=summaries[:500],
        )

    # ── Text utilities (also used by StoryClusteringEngine for title matching) ─

    @staticmethod
    def normalise(text: str) -> set[str]:
        """Return the token set of a lowercased, punctuation-stripped title."""
        cleaned = re.sub(r"[^a-z0-9 ]", " ", text.lower())
        return {t for t in cleaned.split() if t not in _STOP and len(t) > 2}

    @staticmethod
    def jaccard(a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two token sets. Empty sets → 0."""
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)
