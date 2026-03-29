# Architecture

## High-level view

FantasyCabinet uses a Dockerized client/server architecture:

- **Web app**: Next.js TypeScript client for gameplay UX
- **API**: FastAPI service for cabinet scope, cabinet, mandate, policy, scoring, and auth orchestration
- **Worker**: asynchronous processing for event ingestion and scoring jobs
- **PostgreSQL**: system of record
- **Redis**: cache, queues, and rate-limiting support
- **Authentik**: external identity provider via OIDC/OAuth2

## Component responsibilities

### Web (`apps/web`)

- OIDC login redirect and session bootstrap
- Federal/provincial cabinet dashboards, mandate configuration UI, and portfolio workflows
- Score breakdown and event audit timelines
- Scope commissioner controls and dispute workflows

### API (`services/api`)

- AuthN/AuthZ integration with Authentik claims
- Domain APIs: users, cabinet scopes, cabinets, portfolio seats, events, policies, scores, standings
- Rule evaluation orchestration and score ledger writes
- Audit log writing and immutable event references

### Worker (`services/worker`)

- Event ingestion from configured public sources
- Event normalization and deduplication
- Scoring computation jobs
- Notification fanout triggers

## Engine subsystems

### BootstrapEngine (`api/v1/bootstrap_engine.py`)

Runs on startup when the `politicians` table is empty. Fetches current federal ministers from the **Parliament of Canada OData API** (`api.ourcommons.ca`) and merges with a curated 2025-26 fallback list (always available). Writes `DataSourceModel` rows: one Google News RSS per politician plus canonical feeds (CBC Politics, CTV News Politics, Globe and Mail Politics). All feed configuration lives in the database — the worker never has hardcoded URLs.

### AttributionEngine (`api/v1/attribution.py`)

Runs after every ingest batch (`POST /internal/attribution/run`). Scans each event's title + summary against every active politician's `full_name` tokens, `aliases_json`, and `current_role`. Writes one `EventAttributionModel` row per `(event, politician)` match at or above the confidence floor (0.65).

| Attribution type | Confidence |
|-----------------|------------|
| direct_name | 0.95 |
| alias | 0.90 |
| role_title | 0.65 |

### ScoringEngine (`api/v1/scoring_engine.py`)

Fully replaces inline scoring logic. Loads `scoring_rules` from the database at runtime — rules are data, not code. For each active roster slot, queries `event_attributions`, applies the matching `(event_type, asset_type)` rule, attribution confidence multiplier, and an optional AI significance multiplier. Every `score_ledger_entries` row includes an `attribution_id` FK for complete traceability. Commissioners can adjust rule weights via the database without redeployment.

### AIClient (`api/v1/ai_client.py`)

Thin wrapper around the Ollama HTTP API. Configurable at runtime via `system_config` (no restart required):

- `ai_enabled` — default: `false`
- `ai_base_url` — default: `http://10.11.235.71:11434`
- `ai_model` — default: `mistral`
- `ai_confidence_weight` — contribution weight of AI multiplier on final score (0.0–1.0, default 0.3)

All AI calls are best-effort; scoring falls back to rule-only if Ollama is unavailable or times out.

## Admin configuration

System behaviour is configurable at runtime via `GET/PATCH /api/v1/admin/config` (commissioner-gated). Config is stored in the `system_config` table as typed key/value pairs. Changes take effect on the next scoring cycle — no restart required.

## Multi-user design

- Politicians, events, attributions, and scoring rules are **global** — shared across all users and scopes.
- `Cabinet` (team) and `PortfolioSeat` (roster slot) are **per-user** — each manager has their own cabinet.
- Commissioner role is managed by gameplay (`roles` field on `UserModel`), not by a separate identity system.
- Any authenticated user can create a cabinet in an open scope. The commissioner controls scope settings, scoring rules, and politician status.

## Agentic AI development/operations layer

The platform is designed for AI-assisted maintenance:

- **Prompt registry**: versioned prompts for support assistants and ops copilots
- **Policy guardrails**: filters for unsafe or off-policy outputs
- **Runbook automation hooks**: AI suggestions for incident triage
- **Evaluation harness**: replayable test suites for AI-assisted workflows

## Identity and security boundary

- Authentik handles primary user authentication.
- API verifies tokens against OIDC metadata/JWKS.
- Fine-grained authorization is internal (scope role + commissioner rights).
- Service-to-service auth uses internal network trust plus signed service keys.

## Deployment topology

- Local: single `docker compose` stack.
- Future prod: Kubernetes or managed container platform, externalized DB/Redis, managed OTel pipeline, secrets manager.
