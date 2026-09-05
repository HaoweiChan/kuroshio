---
id: DRAFT-49
title: 'target_weight sizes on the recorded invalidation, not the live ratcheted stop'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/allocator/engine.py` `target_weight` reads `h.invalidation_price`, the recorded level, while step 3a now watches a ratcheted stop; a SWAP or TRIM card can quote a target weight computed over a wider risk distance than the run is actually monitoring.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_target_weight_sizes_on_the_live_stop green
<!-- AC:END -->
