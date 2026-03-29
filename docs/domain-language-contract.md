# Domain language contract

This document is the canonical vocabulary for FantasyCabinet.

## Mandatory terms

- **MP (player)**: the playable political actor.
- **Cabinet**: the user-managed team of MPs and portfolio seats.
- **Cabinet scope**: the competition context. Current scopes are:
  - **Federal Cabinet**
  - **Provincial Cabinet**
- **Portfolio seat**: a slot in a cabinet (for example finance, health, house leadership).
- **Mandate**: the weekly governing configuration of active vs monitoring seats.
- **Policy objective**: a strategic goal selected by the user that modifies scoring.
- **Parliamentary event**: a verified public event used for scoring.

## Prohibited terms in user-facing surfaces

- “Franchise”
- Sports drafting language

## Mapping rules for migration and consistency

- Historical backend labels may still exist during migration, but all user-facing text must use this contract.
- New documents, APIs, and UI work must adopt this vocabulary first.
- Any compatibility aliases must be documented as temporary and hidden from default user flows.

## Product identity statement

FantasyCabinet is a fantasy political simulation where users build and run cabinets using MPs, portfolio strategy, and policy choices across federal and provincial contexts.
