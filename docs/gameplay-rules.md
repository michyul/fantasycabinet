# Gameplay rules: FantasyCabinet

## 1) Core concept

FantasyCabinet is a strategy simulation where each user acts as a political manager. The user builds a cabinet of MPs, assigns portfolio seats, sets policy objectives, and scores points from verified public political events.

The game has two connected arenas:

- **Federal arena**: Prime Minister, cabinet, opposition, federal parties, parliamentary actions.
- **Provincial arena**: Premiers, provincial cabinets/legislatures, intergovernmental interactions.

Canonical terminology is defined in [Domain language contract](domain-language-contract.md).

## 2) Cabinet scope formats

### Standard season scope

- 8 to 16 managers per cabinet scope.
- Season length: configurable (default 12 weeks).
- Weekly standings progression with optional rivalry windows.

### Open ladder scope

- Persistent ranking over rolling windows (e.g., 30 days).
- ELO-style movement based on weekly score percentile.

### Tournament mode

- Short event-based competitions during election periods or major sittings.

## 3) Cabinet composition

**Full game design** (all slots):

- **Federal slots**
  - 1x Head of Government (PM or equivalent)
  - 3x Cabinet/Shadow cabinet portfolios
  - 2x Parliamentary influence (whip, house leader, committee chair)
  - 1x Federal policy momentum (party-level)

- **Provincial slots**
  - 2x Premier/Government leadership
  - 4x Provincial cabinet/critical portfolio
  - 2x Provincial opposition or balance-of-power

- **Wildcard slots**
  - 2x Any eligible MP across federal/provincial pools

**MVP (current implementation):** 6 portfolio seats per cabinet (4 governing, 2 monitoring). Full slot counts are the target for the next release.

## 4) Government formation mechanics

- Each manager sets a governing mandate from available cabinet seats.
- Slate changes are strategic and can be adjusted between scoring cycles.
- The experience is policy/portfolio management, not sports drafting.

## 4.1) Party and caucus constraints

- Every MP belongs to a party and jurisdiction.
- Cabinets can include cross-party strategy only if enabled by scope settings.
- Party concentration caps can be applied to avoid one-party overloading.
- Optional caucus rules can require minimum representation from specific jurisdictions.

## 5) Weekly lifecycle

1. **Lock window**: mandates lock before first weekly scoring event cutoff.
2. **Event ingestion**: verified data events are ingested continuously.
3. **Scoring run**: worker computes points per event, party/policy modifiers, and applies caps.
4. **Review window**: managers can view event ledger and challenge anomalies.
5. **Finalize**: week closes and standings update.

## 5.1) Governing slate vs monitoring slate rules

- Each cabinet has 6 portfolio seats in the current MVP.
- Exactly 4 slots must be marked **governing**; remaining slots are **monitoring**.
- At least 1 governing slot must be federal and at least 1 must be provincial.
- Only governing slots can earn points during scoring.
- Monitoring decisions are part of core strategy and should be revisited each cycle as new events arrive.

## 5.2) Policy objective selection

- Before each cycle, users can choose policy objectives (economy, health, housing, climate, intergovernmental).
- Policy objectives grant small multipliers when events match active objectives.
- Objective stacking is capped to keep scoring balanced.

## 6) Scoring categories (high-level)

- Legislative effectiveness
- Executive influence and stability
- Policy delivery milestones
- Public accountability and ethics impact
- Intergovernmental outcomes (federal-provincial dynamics)
- Coalition and confidence dynamics

Detailed scoring values are in [Scoring model](scoring-model.md).

## 7) Fairness and anti-abuse

- Event sources must pass trust policies and deduplication checks.
- Points are immutable once final unless a governed correction event is issued.
- Suspicious score spikes trigger anomaly review.
- Scope commissioners can apply transparent corrections with public audit log.
- Bot and collusion detection for coordinated manipulation attempts.

## 8) Engagement mechanics

- Weekly objectives (e.g., diversify federal/provincial exposure).
- Rivalry bonuses for direct matchup narrative events.
- Prediction side-challenges with capped impact.
- Streak badges and season-long achievements.
- Mandate optimization loop: users can move assets between governing and monitoring status before scoring cycles.

## 9) Content and integrity policy

- Platform is gameplay-focused and nonpartisan in scoring logic.
- No endorsement prompts or manipulative political messaging.
- Event scoring is based on predefined rulebook, not sentiment preference.
