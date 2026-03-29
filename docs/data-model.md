# Data model

## Primary entities

- `User`
- `CabinetScope`
- `Cabinet`
- `PortfolioSeat`
- `MP`
- `ParliamentaryEvent`
- `ScoreLedgerEntry`
- `StandingSnapshot`
- `MandateChange`
- `PolicyObjective`
- `PolicySelection`
- `AuditLog`
- `RulesetVersion`

## Core relationships

- `User` 1..* `Cabinet`
- `CabinetScope` 1..* `Cabinet`
- `Cabinet` 1..* `PortfolioSeat`
- `MP` 1..* `PortfolioSeat`
- `ParliamentaryEvent` 1..* `ScoreLedgerEntry`
- `RulesetVersion` 1..* `ScoreLedgerEntry`

## Suggested table fields (minimum)

### users

- id (UUID)
- external_subject (from OIDC)
- display_name
- email
- created_at, updated_at

### cabinet_scopes

- id (UUID)
- name
- scope_type (federal/provincial)
- format (season/ladder/tournament)
- settings_json
- commissioner_user_id
- current_ruleset_version_id

### mps

- id (UUID)
- jurisdiction (federal/province code)
- party_id
- role_type
- canonical_name
- eligibility_tags
- status

### parliamentary_events

- id (UUID)
- source_name
- source_event_id
- occurred_at
- canonical_type
- payload_json
- trust_score
- dedupe_hash

### score_ledger_entries

- id (UUID)
- cabinet_scope_id
- cabinet_id
- portfolio_seat_id
- event_id
- points
- multiplier
- rule_id
- ruleset_version_id
- correction_of_entry_id (nullable)
- created_at

### politicians

- id (stable string, e.g. `pol-mark-carney`)
- full_name
- aliases_json (array of name variants for attribution matching)
- current_role
- role_tier (1–5: 1 = PM/Premier, 2 = Deputy/Finance, 3 = Cabinet, 4 = Parliamentary, 5 = Critic/Opposition)
- party
- jurisdiction (federal | ON | QC | BC | AB | MB | NS | SK | NB | NL | PE)
- asset_type (executive | cabinet | opposition | parliamentary)
- status (active | pending | ineligible | retired)
- source (bootstrap origin: ourcommons | wikidata | curated)
- last_verified_at

### politician_role_history

- id
- politician_id (FK → politicians)
- previous_role
- new_role
- previous_tier
- new_tier
- changed_at
- changed_by_user_id

### event_attributions

- id
- event_id (FK → political_events)
- politician_id (FK → politicians)
- attribution_type (direct_name | alias | role_title)
- confidence (float, 0.65–0.95)
- matched_text
- created_at

### data_sources

- id
- name
- source_type (rss | api | webhook)
- url_template (may contain `{full_name}`, `{jurisdiction}` placeholders)
- config_json (weight, trust, future API credentials)
- active
- politician_id (FK → politicians, nullable — null = canonical feed)
- created_at

### scoring_rules

- id
- rule_version (e.g. `v1`)
- event_type
- asset_type
- base_points
- affinity_bonus
- jurisdiction_scope (own | any)
- description
- active

### system_config

- key (ai_enabled | ai_base_url | ai_model | ai_confidence_weight | attribution_confidence_floor | scoring_rule_version | bootstrap_sources)
- value_json
- updated_at
- updated_by

## Data governance

- Immutable score ledger rows; corrections are append-only.
- PII minimized to account and cabinet-scope administration needs.
- Soft-delete patterns for user-generated entities where required.
