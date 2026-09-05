---
id: DRAFT-52
title: 'rating_table scores stops against closes only, though Panel.low now exists'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/ledger.py` `rating_table` marks a rating stopped only on a close below the stop; an intraday low that pierced the stop and closed above it reads as not stopped, though `Panel.low` (TASK-11) can now answer that.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_rating_table_uses_the_intraday_low_when_present green
<!-- AC:END -->
