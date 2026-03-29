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
