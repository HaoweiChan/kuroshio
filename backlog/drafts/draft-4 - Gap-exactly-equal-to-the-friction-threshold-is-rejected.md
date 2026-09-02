---
id: DRAFT-4
title: Gap exactly equal to the friction threshold is rejected
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T15
  - 'PR #4 R4'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
the gate is `if gap < hurdle` where `hurdle = ips.turnover.hurdle + friction_pct / 100`, so a gap exactly equal to the threshold should be proposed per the spec's `>=`. Float representation defeats it: with hurdle 0.15 and TW friction 0.585 the threshold is 0.15585, while a challenger at 0.55585 against an incumbent at 0.40 gives a gap of 0.15584999999999993 and is rejected.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the boundary is decided deliberately (an epsilon, or rounding to score precision) and pinned by a test asserting what happens when the gap equals hurdle + friction/100 exactly.
<!-- AC:END -->
