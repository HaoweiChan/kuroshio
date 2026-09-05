---
id: DRAFT-53
title: 'a trailed setup with an entry_date but no ATR is not named on the coverage card'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/allocator/engine.py` step 3a stays silent when a `trend_add` or cleared `pullback_add` has an `entry_date` but the panel yields no ATR14 (a FinMind response without max/min, or fewer than 14 sessions); the position keeps its recorded level without appearing on the 'not fully monitored' line.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_missing_atr_is_named_on_the_coverage_card green
<!-- AC:END -->
