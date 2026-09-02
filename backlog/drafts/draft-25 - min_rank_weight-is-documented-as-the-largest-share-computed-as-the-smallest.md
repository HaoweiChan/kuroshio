---
id: DRAFT-25
title: 'min_rank_weight is documented as the largest share, computed as the smallest'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T37
  - 'PR #6 R20'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
six sites define `min_rank_weight` as "the largest share of `final_score` a single pctrank can control" while the code takes the smallest surviving weight: us.py:33 says "Largest share ... the composite at its coarsest" and us.py:38 computes `min(WEIGHTS["momentum"], WEIGHTS["volume"]) / (sum)` = 0.37523, the smaller of (0.62477, 0.37523). Also cli.py:268, the cli.py:296 notice ("this market's single coarsest factor weight"), docs/ARCHITECTURE.md:212-213, docs/adding-a-market.md:81 and core/screening/__init__.py:26. TW is unaffected — its degraded weights are equal, so largest == smallest. The consequence with teeth: adding-a-market.md instructs a new market's author to compute the max, which for a 0.625/0.375-shaped profile yields `need` = 6 where us.py's own rule yields 4. "Conservative, never permissive" is only derivable from the minimum per-pctrank weight, not from the definition given. Merged as named debt at the human's direction (option B at the round-6 circuit breaker); no behaviour is wrong, only the definition.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the six sites describe `min_rank_weight` as the smallest per-pctrank share of the fully degraded composite, or drop the superlative and point at the code. No behaviour change; `need` stays 4 for both markets. Fold in T35 and T36 while there.
<!-- AC:END -->
