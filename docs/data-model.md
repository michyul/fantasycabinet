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

## Data governance

- Immutable score ledger rows; corrections are append-only.
- PII minimized to account and cabinet-scope administration needs.
- Soft-delete patterns for user-generated entities where required.
