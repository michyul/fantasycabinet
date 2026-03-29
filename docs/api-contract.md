# API contract (initial)

Base path: `/api/v1`

## Auth and profile

- `GET /auth/me`
- `POST /auth/logout`

## Cabinet scopes

- `GET /cabinet-scopes`
- `POST /cabinet-scopes`
- `GET /cabinet-scopes/{scopeId}`
- `PATCH /cabinet-scopes/{scopeId}`

## Cabinets, MPs, and portfolio seats

- `GET /cabinet-scopes/{scopeId}/cabinets`
- `POST /cabinet-scopes/{scopeId}/cabinets`
- `GET /cabinets/{cabinetId}/portfolio`
- `PATCH /cabinets/{cabinetId}/mandate`
- `GET /cabinets/{cabinetId}/mps`

## Scoring and standings

- `GET /cabinet-scopes/{scopeId}/scores?week={week}`
- `GET /cabinet-scopes/{scopeId}/standings`
- `GET /cabinets/{cabinetId}/ledger?week={week}`

## Policy objectives

- `GET /cabinet-scopes/{scopeId}/policy-objectives`
- `PUT /cabinets/{cabinetId}/policy-objectives`
- `GET /cabinets/{cabinetId}/policy-objectives`

## Governance

- `POST /cabinet-scopes/{scopeId}/disputes`
- `POST /cabinet-scopes/{scopeId}/disputes/{disputeId}/resolve`
- `GET /cabinet-scopes/{scopeId}/audit-log`

## Event ingestion (service/internal)

- `POST /internal/events/ingest`
- `POST /internal/scoring/run`

OpenAPI starter is in [packages/contracts/openapi.yaml](../packages/contracts/openapi.yaml).
