# Agentic AI operations and maintenance

## Goals

- Accelerate feature development, triage, and operations.
- Preserve safety, auditability, and reproducibility.
- Keep AI systems assistive, not autonomous over critical production actions.

## Recommended stack

- **Backend agent framework**: LangGraph or Semantic Kernel for durable workflows.
- **Model gateway**: support for multiple providers via abstraction layer.
- **Prompt registry**: versioned prompt templates in source control.
- **Evaluation harness**: regression datasets for gameplay and moderation scenarios.
- **Vector store (optional)**: retrieval for docs, rulebooks, runbooks.

## Agent categories

- **Support assistant**: user-facing help for cabinet mechanics and rule explanations.
- **Commissioner copilot**: dispute triage and suggested actions (human approval required).
- **Ops copilot**: incident summarization and runbook recommendations.
- **Developer copilot workflows**: code quality checks and change impact summaries.

## Guardrails

- No direct write access to score ledger without explicit, authorized API path.
- Sensitive actions require human-in-the-loop approval.
- Policy checks before response delivery.
- Full traceability: prompt, model, context IDs, and output hash in audit store.

## AI observability

- Track latency, cost, token usage, and refusal rates.
- Capture quality metrics on predefined test suites.
- Alert on drift in recommendation quality.

## Maintenance workflow

1. Propose prompt/model change in ADR.
2. Run evaluation harness.
3. Review security/privacy impacts.
4. Deploy behind feature flag.
5. Monitor and roll back quickly on regressions.
