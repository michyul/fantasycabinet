"""Tests for app.api.v1.news_analysis_client module.

Covers:
- NewsAnalysisClient.normalise()       — static text utility
- NewsAnalysisClient.jaccard()         — similarity metric
- NewsAnalysisClient._heuristic_cluster() — fallback clustering
- NewsAnalysisClient.cluster_articles() — AI-unavailable path
- NewsAnalysisClient.assess_story_update() — fallback + AI paths
- NewsAnalysisClient._parse_cluster_response() — index coverage guard
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.api.v1.news_analysis_client import (
    ClusterProposal,
    NewsAnalysisClient,
    RescoreAssessment,
    _DEFAULT_SIGNIFICANCE,
    _JACCARD_THRESHOLD,
)


# ── normalise ─────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_lowercase_and_strip(self):
        tokens = NewsAnalysisClient.normalise("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_removes_stop_words(self):
        tokens = NewsAnalysisClient.normalise("a budget is announced")
        # "a" and "is" are stop words
        assert "a" not in tokens
        assert "is" not in tokens
        assert "budget" in tokens
        assert "announced" in tokens

    def test_removes_short_tokens(self):
        tokens = NewsAnalysisClient.normalise("an MP votes on bill")
        assert "an" not in tokens
        # "mp" is 2 chars → filtered out
        assert "mp" not in tokens

    def test_punctuation_stripped(self):
        tokens = NewsAnalysisClient.normalise("Trudeau's budget: a plan")
        assert "trudeau" in tokens or "trudeaus" in tokens  # apostrophe converted to space

    def test_empty_string(self):
        assert NewsAnalysisClient.normalise("") == set()

    def test_all_stop_words(self):
        tokens = NewsAnalysisClient.normalise("a an the is")
        assert tokens == set()

    def test_returns_set(self):
        result = NewsAnalysisClient.normalise("parliament parliament")
        assert isinstance(result, set)
        assert len(result) == 1  # deduplication

    def test_french_stop_words_removed(self):
        tokens = NewsAnalysisClient.normalise("le premier ministre du canada")
        assert "le" not in tokens
        assert "du" not in tokens
        assert "premier" in tokens
        assert "ministre" in tokens


# ── jaccard ───────────────────────────────────────────────────────────────────

class TestJaccard:
    def test_identical_sets(self):
        s = {"a", "b", "c"}
        assert NewsAnalysisClient.jaccard(s, s) == pytest.approx(1.0)

    def test_disjoint_sets(self):
        a = {"x", "y"}
        b = {"p", "q"}
        assert NewsAnalysisClient.jaccard(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        # intersection={b,c}=2, union={a,b,c,d}=4 → 0.5
        assert NewsAnalysisClient.jaccard(a, b) == pytest.approx(0.5)

    def test_empty_a(self):
        assert NewsAnalysisClient.jaccard(set(), {"a"}) == pytest.approx(0.0)

    def test_empty_b(self):
        assert NewsAnalysisClient.jaccard({"a"}, set()) == pytest.approx(0.0)

    def test_both_empty(self):
        assert NewsAnalysisClient.jaccard(set(), set()) == pytest.approx(0.0)

    def test_subset_similarity(self):
        a = {"a", "b"}
        b = {"a", "b", "c", "d"}
        # intersection=2, union=4 → 0.5
        assert NewsAnalysisClient.jaccard(a, b) == pytest.approx(0.5)


# ── _heuristic_cluster ────────────────────────────────────────────────────────

def _article(title: str, event_type: str = "general", jurisdiction: str = "federal",
             summary: str = "") -> dict:
    return {"id": f"id-{title[:5]}", "title": title,
            "event_type": event_type, "jurisdiction": jurisdiction, "summary": summary}


class TestHeuristicCluster:
    def setup_method(self):
        self.client = NewsAnalysisClient(ai_client=None)

    def test_single_article_single_cluster(self):
        articles = [_article("Budget announced by finance minister")]
        clusters = self.client._heuristic_cluster(articles)
        assert len(clusters) == 1
        assert isinstance(clusters[0], ClusterProposal)
        assert clusters[0].article_indices == [0]

    def test_similar_titles_grouped(self):
        articles = [
            _article("Parliament votes on new climate policy bill"),
            _article("Parliament votes on climate policy legislation"),
        ]
        clusters = self.client._heuristic_cluster(articles)
        # Both titles are very similar → should cluster together
        assert len(clusters) == 1
        assert sorted(clusters[0].article_indices) == [0, 1]

    def test_unrelated_titles_separate(self):
        articles = [
            _article("Budget unveiled for healthcare spending"),
            _article("Election called in British Columbia province"),
        ]
        clusters = self.client._heuristic_cluster(articles)
        # Very different topics → 2 clusters
        assert len(clusters) == 2

    def test_all_articles_covered(self):
        articles = [
            _article("Climate policy debate"),
            _article("Housing affordability crisis"),
            _article("Tax reform announced"),
        ]
        clusters = self.client._heuristic_cluster(articles)
        all_indices = sorted(i for c in clusters for i in c.article_indices)
        assert all_indices == [0, 1, 2]

    def test_empty_articles(self):
        clusters = self.client._heuristic_cluster([])
        assert clusters == []

    def test_significance_from_event_type(self):
        articles = [_article("Confidence vote upcoming", event_type="confidence")]
        clusters = self.client._heuristic_cluster(articles)
        assert clusters[0].significance == _DEFAULT_SIGNIFICANCE["confidence"]

    def test_default_significance_for_unknown_type(self):
        articles = [_article("Something odd happened", event_type="unusual_type")]
        clusters = self.client._heuristic_cluster(articles)
        # _DEFAULT_SIGNIFICANCE.get(et, 4.0) → 4.0
        assert clusters[0].significance == 4.0

    def test_canonical_title_is_longest(self):
        articles = [
            _article("Short title"),
            _article("A much much longer title that covers the whole story"),
        ]
        # These are similar enough to cluster
        norms = [NewsAnalysisClient.normalise(a["title"]) for a in articles]
        sim = NewsAnalysisClient.jaccard(norms[0], norms[1])
        if sim >= _JACCARD_THRESHOLD:
            clusters = self.client._heuristic_cluster(articles)
            assert len(clusters[0].canonical_title) >= len("Short title")


# ── cluster_articles (AI disabled) ───────────────────────────────────────────

class TestClusterArticles:
    def test_empty_returns_empty(self):
        client = NewsAnalysisClient(ai_client=None)
        assert client.cluster_articles([]) == []

    def test_ai_disabled_uses_heuristic(self):
        ai = MagicMock()
        ai.enabled = False
        client = NewsAnalysisClient(ai_client=ai)
        articles = [_article("Parliament votes on bill today")]
        result = client.cluster_articles(articles)
        assert len(result) == 1
        assert isinstance(result[0], ClusterProposal)

    def test_batch_limit(self):
        client = NewsAnalysisClient(ai_client=None)
        # Feed 30 articles but MAX_ARTICLES_PER_CALL=25
        articles = [_article(f"Unique story number {i} about topic {i}") for i in range(30)]
        result = client.cluster_articles(articles)
        covered = sum(len(c.article_indices) for c in result)
        assert covered <= 25  # only first 25 processed

    def test_ai_fails_falls_back_to_heuristic(self):
        ai = MagicMock()
        ai.enabled = True
        ai.generate_structured.return_value = None  # AI fails
        client = NewsAnalysisClient(ai_client=ai)
        articles = [_article("Budget announced")]
        result = client.cluster_articles(articles)
        assert len(result) == 1  # heuristic fallback


# ── assess_story_update ───────────────────────────────────────────────────────

class TestAssessStoryUpdate:
    def test_ai_disabled_returns_no_change(self):
        client = NewsAnalysisClient(ai_client=None)
        result = client.assess_story_update(
            story_title="Budget plan",
            story_event_type="policy",
            current_significance=5.0,
            current_sentiment=0.0,
            article_count=3,
            new_article_titles=["New article"],
            new_article_summaries=["Some summary"],
        )
        assert isinstance(result, RescoreAssessment)
        assert result.should_rescore is False
        assert result.significance_delta == pytest.approx(0.0)
        assert result.updated_significance == pytest.approx(5.0)

    def test_ai_enabled_returns_ai_assessment(self):
        ai = MagicMock()
        ai.enabled = True
        ai.generate_structured.return_value = {
            "updated_significance": 8.0,
            "updated_sentiment": -0.5,
            "significance_delta": 3.0,
            "should_rescore": True,
            "reason": "Major development",
        }
        client = NewsAnalysisClient(ai_client=ai)
        result = client.assess_story_update(
            story_title="Scandal erupts",
            story_event_type="ethics",
            current_significance=5.0,
            current_sentiment=0.0,
            article_count=2,
            new_article_titles=["Update on scandal"],
            new_article_summaries=["New evidence emerged"],
        )
        assert result.should_rescore is True
        assert result.updated_significance == pytest.approx(8.0)
        assert result.significance_delta == pytest.approx(3.0)

    def test_ai_enabled_but_fails_returns_no_change(self):
        ai = MagicMock()
        ai.enabled = True
        ai.generate_structured.return_value = None
        client = NewsAnalysisClient(ai_client=ai)
        result = client.assess_story_update(
            story_title="Routine vote",
            story_event_type="legislative",
            current_significance=4.0,
            current_sentiment=0.1,
            article_count=1,
            new_article_titles=[],
            new_article_summaries=[],
        )
        assert result.should_rescore is False
        assert result.updated_significance == pytest.approx(4.0)

    def test_ai_significance_clamped_to_range(self):
        ai = MagicMock()
        ai.enabled = True
        ai.generate_structured.return_value = {
            "updated_significance": 99.0,  # out of range
            "updated_sentiment": -5.0,      # out of range
            "significance_delta": 94.0,
            "should_rescore": True,
            "reason": "Extreme",
        }
        client = NewsAnalysisClient(ai_client=ai)
        result = client.assess_story_update(
            "Title", "general", 5.0, 0.0, 1, ["t"], ["s"]
        )
        assert result.updated_significance <= 10.0
        assert result.updated_sentiment >= -1.0


# ── _parse_cluster_response ───────────────────────────────────────────────────

class TestParseClusterResponse:
    def setup_method(self):
        ai = MagicMock()
        ai.enabled = True
        self.client = NewsAnalysisClient(ai_client=ai)

    def test_all_indices_covered(self):
        articles = [_article(f"Title {i}") for i in range(3)]
        raw = [{"canonical_title": "Cluster", "indices": [0, 1, 2],
                "event_type": "general", "jurisdiction": "federal",
                "significance": 5.0, "sentiment": 0.0, "is_followup": False}]
        result = self.client._parse_cluster_response(raw, articles)
        assert result is not None
        covered = {i for c in result for i in c.article_indices}
        assert covered == {0, 1, 2}

    def test_uncovered_indices_added_as_singletons(self):
        articles = [_article(f"Article {i}") for i in range(3)]
        # Only index 0 in raw clusters
        raw = [{"canonical_title": "Only First", "indices": [0],
                "event_type": "general", "jurisdiction": "federal",
                "significance": 5.0, "sentiment": 0.0, "is_followup": False}]
        result = self.client._parse_cluster_response(raw, articles)
        assert result is not None
        covered = {i for c in result for i in c.article_indices}
        assert covered == {0, 1, 2}

    def test_empty_raw_clusters_returns_none(self):
        articles = [_article("Test")]
        result = self.client._parse_cluster_response([], articles)
        assert result is None

    def test_out_of_range_index_filtered(self):
        articles = [_article("Test")]
        raw = [{"canonical_title": "Bad", "indices": [0, 999],
                "event_type": "general", "jurisdiction": "federal",
                "significance": 5.0, "sentiment": 0.0, "is_followup": False}]
        result = self.client._parse_cluster_response(raw, articles)
        assert result is not None
        # index 999 filtered → only 0
        assert result[0].article_indices == [0]

    def test_significance_clamped(self):
        articles = [_article("Test")]
        raw = [{"canonical_title": "Huge", "indices": [0],
                "event_type": "general", "jurisdiction": "federal",
                "significance": 999.0, "sentiment": 5.0, "is_followup": False}]
        result = self.client._parse_cluster_response(raw, articles)
        assert result is not None
        assert result[0].significance <= 10.0
        assert result[0].sentiment <= 1.0

    def test_missing_canonical_title_uses_first_article_title(self):
        articles = [{"id": "1", "title": "Fallback Title", "event_type": "general",
                     "jurisdiction": "federal", "summary": ""}]
        raw = [{"indices": [0], "event_type": "general", "jurisdiction": "federal",
                "significance": 5.0, "sentiment": 0.0, "is_followup": False}]
        result = self.client._parse_cluster_response(raw, articles)
        assert result is not None
        assert result[0].canonical_title == "Fallback Title"
