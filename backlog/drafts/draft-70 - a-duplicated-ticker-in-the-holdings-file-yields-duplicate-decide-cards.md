---
id: DRAFT-70
title: 'a duplicated ticker in the holdings file yields duplicate DECIDE cards'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #42 (TASK-16)
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_holdings_from_yaml` accepts the same ticker twice, and both the MAE step and the new rating-veto step (3d) in `kuroshio/core/allocator/engine.py` iterate holdings row by row, so a duplicated row produces two identical DECIDE cards per run. Reject duplicates once in the loader (a real holdings file never has two rows for one ticker) rather than deduping in each step. Reported as a non-blocking LOW by the TASK-16 verifier; the MAE half is pre-existing.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case a holdings file with the same ticker twice fails the loader with a message naming the ticker, and propose emits one DECIDE per ticker
<!-- AC:END -->
