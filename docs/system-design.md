# System design

## Core bounded contexts

- **Identity & Access**
- **Cabinet Scope Management**
- **Portfolio Seats & Transactions**
- **Event Ingestion**
- **Scoring Engine**
- **Standings & Rewards**
- **Audit & Governance**

## Key runtime flows

### Login flow

1. User opens web app.
2. Web redirects to Authentik OIDC authorize endpoint.
3. Callback exchanges code for tokens.
4. API validates identity claims and provisions local profile.

### Weekly scoring flow

1. Worker fetches new source events.
2. Normalizer maps raw events to canonical event schema.
3. Deduplicator ensures idempotency.
4. Scoring engine applies active ruleset.
5. API persists score ledger and updates standings snapshots.

### Dispute flow

1. Manager flags scoring event.
2. Commissioner reviews provenance and rule mapping.
3. If correction is approved, worker emits correction event.
4. Ledger appends correction entry (no destructive edits).

## Non-functional targets

- Availability target (initial): 99.5%
- End-user p95 page load target: < 2.5s on core dashboards
- Scoring batch completion: < 5 min per weekly cycle baseline
- Audit log retention: minimum 2 years (configurable)

## Observability

- OpenTelemetry traces for API and worker jobs
- Structured logs with request and correlation IDs
- Metrics: ingestion lag, scoring throughput, queue depth, auth failures

## Extensibility

- Pluggable event connectors per source
- Ruleset versions by cabinet scope
- Feature flags for experimental mechanics
