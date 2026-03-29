# Scoring model

## Principles

1. **Story-based, not article-based**: scoring is driven by canonical *news stories* — 100 articles about the same cabinet reshuffle count as one story.
2. **AI-augmented, deterministically floored**: the engine uses Ollama to assess story significance (1–10) and sentiment (−1 to +1). AI contribution is bounded by `ai_confidence_weight` so rules remain the floor.
3. **Self-correcting**: stories can be re-scored up to three times as significance evolves. Corrections appear as delta ledger entries.
4. **Transparent and auditable**: every ledger entry links to `story_id`, `attribution_id`, `politician_id`, and `rule_id`.
5. **Inflation-resistant**: per-story caps, follow-up discounts, and the sentiment factor prevent a single viral story from dominating a week.

---

## Full pipeline

```
RSS feeds (worker, every ~60 s)
        │
        ▼
PoliticalEventModel          ingest_events → returns inserted_ids
        │  story_id = NULL
        ▼
StoryClusteringEngine        news_analysis_client: AI cluster or Jaccard fallback
        │
        ▼
NewsStoryModel               canonical_title, significance (1–10), sentiment (−1–1)
        │
        ▼
AttributionEngine            EventAttributionModel: politician → story articles
        │  confidence ≥ 0.65
        ▼
ScoringEngine                score_teams_for_stories() → ScoringResult list
        │
        ▼
LedgerEntryModel             story_id, attribution_id, politician_id, rule_id
        │
        └─ Re-score check (story.rescore_pending = True)
              │ if |Δsignificance| ≥ 1.5
              ▼
           correction LedgerEntryModel    [CORRECTION] prefix, up to 3×
```

---

## Story clustering

The `StoryClusteringEngine` runs after every ingest batch. It takes all `PoliticalEventModel` rows where `story_id IS NULL` and groups them into `NewsStoryModel` records.

### AI clustering (preferred)

A single structured Ollama call (`format: "json"`) receives up to 25 article titles + summaries and returns:

```json
{
  "clusters": [
    {
      "canonical_title": "Federal budget passes third reading",
      "event_type": "legislative",
      "jurisdiction": "federal",
      "significance": 7.5,
      "sentiment": 0.2,
      "is_followup": false,
      "indices": [0, 2, 4]
    }
  ]
}
```

Every article index appears in exactly one cluster. The engine validates schema, caps significance to [1, 10] and sentiment to [−1, 1], and ensures no articles are dropped.

### Heuristic fallback (AI unavailable)

Jaccard similarity on normalised title token sets (stop-words removed):

- Similarity ≥ 0.45 → same story
- Canonical title = longest title in cluster
- Default significance from event_type table
- Sentinel sentiment = 0.0 (neutral)

### Default significance by event_type

| Event type | Default significance |
|------------|---------------------|
| confidence | 8.0 |
| ethics | 6.5 |
| election | 6.0 |
| intergovernmental | 5.5 |
| legislative | 5.5 |
| executive | 5.0 |
| policy | 4.5 |
| opposition | 4.0 |
| general | 3.0 |

---

## Story lifecycle

| Status | Condition | Behaviour |
|--------|-----------|-----------|
| `active` | < 24 h old | Accepts new articles; re-scoring triggered when delta-significance >= 1.5 |
| `settling` | 24–48 h old | New articles still cluster in; higher delta threshold (2.5) for re-score |
| `archived` | > 48 h old | No further scoring updates |

---

## Scoring formula

For each (team, active_slot, story) triple where the slot's politician is attributed to the story:

```
S_raw = BasePoints x SignificanceMultiplier x FollowupDiscount x SentimentFactor x ConfidenceMultiplier
S_final = clamp(S_raw + PolicyBonus x SignificanceMultiplier, -S_cap, +S_cap)
```

where S_cap = max_story_points (default 15, configurable in system_config).

### Significance multiplier

```
SignificanceMultiplier = significance / 5.0
```

A story with significance 5 scores at 1x base. Significance 10 = 2x. Significance 1 = 0.2x.

### Follow-up discount

Follow-up coverage (subsequent articles about an ongoing story) scores at 50% of normal points.

### Sentiment factor

The story sentiment (-1 to +1) affects scores differently by asset_type:

| Asset type | Sentiment +1.0 | Sentiment -1.0 |
|------------|---------------|----------------|
| executive / cabinet | 1.25x | 0.50x |
| opposition | 0.875x | 1.25x |
| parliamentary | 1.00x | 0.80x |

Government scandals (negative sentiment) reduce executive/cabinet scores and boost opposition scores. Positive government news reverses this.

### Attribution confidence multiplier

| Type | Confidence | Point multiplier |
|------|-----------|------------------|
| direct_name | 0.95 | 1.00 |
| alias | 0.90 | 0.95 |
| role_title | 0.65 | 0.60 |

Attribution confidence floor: **0.65** — stories not attributed at this level score zero for that politician.

Story-level attributions are derived by aggregating all article-level attributions within a story, grouping by politician, and keeping the highest-confidence attribution per politician.

### Per-story cap

No single story can award more than +/-max_story_points (default 15) to any team in any week.

---

## Re-scoring (corrections)

When a story's significance changes by >= 1.5 points (via new AI assessment or admin update):

1. Look up all existing ledger entries for (story_id, team_id, week, league_id).
2. Calculate correction = new_score - old_total.
3. If |correction| >= 1: write a correction LedgerEntryModel with event title "[CORRECTION] {canonical_title}".
4. Increment story.score_version and story.rescore_count.
5. Maximum 3 re-scores per story.

---

## Weekly score formula

```
FinalScore(w) = sum over active slots of Score(slot, w) + PolicyBonus(w) - Penalty(w)
```

PolicyBonus fires when at least one story in the week matches a policy objective's event_types.

### Ineligibility penalty (deferred)

Applied at the start of the next cycle, not mid-week:

| Change | Points |
|--------|--------|
| status -> ineligible | -3 for all teams holding them |
| Promotion (role_tier decreases) | +5 for teams holding them |
| Lateral (role_tier unchanged) | +2 for teams holding them |

---

## Base point table (rule version v1)

| Event type | executive | cabinet | opposition | parliamentary |
|------------|-----------|---------|------------|---------------|
| legislative | 6 | 5 | 4 | 3 |
| executive | 8 | 6 | 3 | 2 |
| policy | 5 | 5 | 4 | 3 |
| confidence | 10 | 8 | 6 | 4 |
| ethics | -8 | -6 | +5 | 2 |
| intergovernmental | 6 | 5 | 3 | 2 |
| opposition | 2 | 2 | 7 | 4 |
| election | 5 | 4 | 5 | 3 |
| leadership_change | 8 | 6 | 5 | 3 |
| general | 2 | 2 | 2 | 1 |

---

## AI significance multiplier (optional)

When ai_enabled = true, NewsAnalysisClient calls Ollama with format:json for structured significance
assessment. The AI contribution is bounded: AI can shift scores by at most +-30% from the rule-only
value at the default ai_confidence_weight = 0.3.

---

## System config keys (scoring-relevant)

| Key | Default | Effect |
|-----|---------|--------|
| ai_enabled | false | Enable Ollama AI calls |
| ai_model | mistral | Ollama model name |
| ai_base_url | http://10.11.235.71:11434 | Ollama endpoint |
| ai_confidence_weight | 0.3 | AI multiplier weight |
| attribution_confidence_floor | 0.65 | Minimum confidence to attribute |
| max_points_per_asset_week | 25 | Weekly per-asset cap (positive) |
| min_points_per_asset_week | -20 | Weekly per-asset cap (negative) |
| max_story_points | 15 | Per-story per-team cap |
| scoring_rule_version | v1 | Active scoring ruleset |
| story_rescore_threshold | 1.5 | Min delta-significance to trigger re-score |
