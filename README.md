# FantasyCabinet

FantasyCabinet is a web-based multiplayer Canadian political simulation. Users assemble cabinets of MPs, assign portfolio strategy, and score from real parliamentary and policy events across federal and provincial cabinet scopes.

## Scope of this initial setup

This first phase establishes:

- Core game design and rules documentation
- Scoring and anti-abuse mechanics
- System architecture and security design
- Dockerized client/server development baseline
- Authentik-ready authentication integration points
- Agentic AI operations framework for maintainability
- Functional MVP APIs for cabinet scopes, cabinets, roster/portfolio seats, standings, scoring run, disputes, and audit log
- Interactive dashboard consuming live API data

## Monorepo structure

- `apps/web`: Next.js frontend (TypeScript)
- `services/api`: FastAPI backend API
- `services/worker`: Async event/scoring worker
- `packages/contracts`: OpenAPI and shared contracts
- `infra/authentik`: Authentik integration notes
- `infra/observability`: OpenTelemetry starter config
- `docs`: Gameplay, architecture, data, API, ADRs, threat model

## Quick start (Docker)

1. Copy `.env.example` to `.env` and fill values.
2. Start stack:

   `docker compose up --build`

3. Open:
   - Web: <http://localhost:3001>
   - API health: <http://localhost:8000/health>

## Implemented functionality (MVP)

- Demo cabinet scope and cabinets are auto-bootstrapped at API startup.
- Web dashboard loads cabinet standings from API.
- "Run week scoring" triggers a scoring cycle and refreshes standings.
- Worker periodically runs automated scoring cycles for all cabinet scopes.
- API includes dispute creation/resolution and per-scope audit log.
- PostgreSQL-backed persistent data for users, cabinet scopes, cabinets, rosters, scores, disputes, and audit logs.
- User management endpoints for create/list/get/update and profile upsert via headers.
- Worker ingests real Canadian politics data from RSS feeds on each cycle.
- API stores normalized real-world political events and scores cabinets from those events.
- Mandate manager UX for choosing governing versus monitoring slots per cabinet.
- Mandate manager now uses split Governing/Monitoring panels, quick actions, and auto-balance.
- Scoring now applies only to governing slots; monitoring slots do not score.
- Enforced mandate strategy: exactly 4 governing slots with at least 1 federal and 1 provincial governing slot.

## Real-data gameplay pipeline

- Worker fetches configured Canadian politics feeds (`WORKER_REAL_DATA_FEEDS`).
- Feed entries are normalized and sent to `POST /api/v1/internal/events/ingest`.
- API deduplicates by source + source event id and persists events.
- Weekly scoring consumes unscored real events first, then applies fallback momentum only when no real events are available.
- Recent ingested events are visible at `GET /api/v1/events`.

## Documentation index

- [Domain language contract](docs/domain-language-contract.md)
- [Game rules and cabinet mechanics](docs/gameplay-rules.md)
- [Scoring model](docs/scoring-model.md)
- [Architecture](docs/architecture.md)
- [System design](docs/system-design.md)
- [Data model](docs/data-model.md)
- [API contract](docs/api-contract.md)
- [Threat model](docs/threat-model.md)
- [Agentic AI ops](docs/agentic-ai-ops.md)
- [ADR template](docs/adr/0001-adr-template.md)

## Status

Foundational documentation and scaffold are complete, and a functional persistent-storage gameplay MVP is implemented. Authentication enforcement is intentionally deferred; next phase is deeper party dynamics, policy-objective gameplay, and richer government-formation flows.
