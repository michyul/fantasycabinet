# Scoring model

## Principles

1. **Deterministic**: identical events always score identically.
2. **Auditable**: every score links to a source event and rule version.
3. **Balanced**: no single category dominates season outcomes.
4. **Nonpartisan**: rules reward measurable activity and outcomes only.

## Weekly score formula

For each active MP-seat assignment $a$ in week $w$:

$$
Score(a,w)=\sum_i BasePoints(event_i)\times ContextMultiplier(event_i) + Bonus(a,w)-Penalty(a,w)
$$

Cabinet weekly score:

$$
CabinetScore(w)=\sum_{a\in ActiveCabinet} Score(a,w)
$$

Active roster constraints in the current MVP:

- $|ActiveCabinet|=4$
- At least one federal active slot
- At least one provincial active slot

Optional policy objective contribution:

$$
PolicyBonus(w)=\sum_j ObjectiveWeight_j\times ObjectiveHitRate_j
$$

Final weekly total:

$$
FinalScore(w)=CabinetScore(w)+PolicyBonus(w)-CompliancePenalty(w)
$$

## Base category points

- **Legislative action**
  - Bill introduced (eligible role): +2
  - Bill advanced stage: +3
  - Bill passed chamber/final assent milestone: +6

- **Executive governance**
  - Cabinet appointment stability event: +2
  - Major portfolio delivery milestone: +5
  - Formal intergovernmental agreement signed: +7

- **Accountability and ethics**
  - Verified ethics breach ruling: -8
  - Official correction/rectification event: +2 (capped)

- **Confidence and coalition dynamics**
  - Confidence vote survival: +5
  - Confidence defeat: -10

- **Provincial-federal coordination**
  - Joint policy framework milestone: +4
  - Public negotiation breakdown with formal cancellation: -3

## Context multipliers

- High-impact national/provincial budget event: $\times1.3$
- Election period bonus window (if cabinet scope enables): $\times1.2$
- Duplicate-event suppression: later duplicates $\times0.0$

## Bonuses

- Balanced roster bonus (minimum asset diversity thresholds): +5/week
- Underdog upset (head-to-head only): +3
- Prediction challenge (capped): +0 to +4
- Policy objective alignment bonus (capped): +0 to +5

## Penalties

- Inactive slot penalty (asset not eligible/active per rules): -2 each
- Overconcentration penalty (too many assets from one domain, optional): -3
- Invalid mandate configuration after lock: zero points for illegal slot

## Caps and safeguards

- Max positive points per single asset per week: +25
- Max negative points per single asset per week: -20
- Category cap to reduce volatility clustering

## Rule versioning

- Each score references `scoring_ruleset_version`.
- Version updates apply only to new weeks unless scope commissioner opts in.
