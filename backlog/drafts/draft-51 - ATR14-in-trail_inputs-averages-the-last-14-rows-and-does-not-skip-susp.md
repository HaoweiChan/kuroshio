---
id: DRAFT-51
title: 'ATR14 in trail_inputs averages the last 14 rows and does not skip suspension holes'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/allocator/signals.py` `_atr` is a plain rolling mean over rows, so a long-suspended ticker averages a stale range — the same gap the MA50 ponytail comment names in `monitor_inputs`.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_atr14_skips_suspension_holes green
<!-- AC:END -->
