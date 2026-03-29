# Threat model

## Method

STRIDE-style review for key data flows and trust boundaries.

## Assets to protect

- User identity and session integrity
- Cabinet state integrity (portfolio seats, scores, standings)
- Event and scoring provenance
- Audit and moderation records

## Key threats and mitigations

### Spoofing

- Threat: forged identity tokens.
- Mitigations: OIDC signature/JWKS validation, issuer/audience checks, nonce/state validation.

### Tampering

- Threat: unauthorized score edits.
- Mitigations: append-only ledger, role-based access, signed correction actions, immutable audit entries.

### Repudiation

- Threat: users deny actions (mandate changes, commissioner decisions).
- Mitigations: auditable action logs with actor, timestamp, request ID.

### Information disclosure

- Threat: PII leakage.
- Mitigations: data minimization, encrypted transit, secure secrets handling, least-privilege DB access.

### Denial of service

- Threat: API flooding and queue saturation.
- Mitigations: rate limiting, backpressure, queue depth alerts, graceful degradation.

### Elevation of privilege

- Threat: manager escalates to commissioner/admin capabilities.
- Mitigations: strict server-side authorization checks, policy tests, privileged action approvals.

## Security backlog (near-term)

- Add dependency vulnerability scanning in CI.
- Add CSP and security headers on web app.
- Add signed webhook verification for external ingestion sources.
