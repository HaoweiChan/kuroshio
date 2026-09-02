---
id: DRAFT-23
title: 'The US `need` value is pinned by a bucket, not a number'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T34
  - 'PR #6 R19 (reviewer note)'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`test_propose_guards_the_us_pool_too` pins that a 3-name US pool refuses and a 4-name pool scores, which constrains `us.MIN_RANK_WEIGHT` only to the interval [0.3004, 0.4506) — any value in that range is a silent no-op, so a wrong derivation inside the bucket ships green. The TW side has the same shape. No test asserts the printed `need` itself.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one case asserts the `need` value the notice prints for each market, so a change to `MIN_RANK_WEIGHT` that stays inside the bucket still goes red.
<!-- AC:END -->
