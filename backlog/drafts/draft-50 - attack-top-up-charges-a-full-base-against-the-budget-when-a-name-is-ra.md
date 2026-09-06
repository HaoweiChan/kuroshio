---
id: DRAFT-50
title: 'attack top-up charges a full base against the budget when a name is raised by less'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #28
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
core/book.py's attack top-up loop charges `base_pct` against the attack budget for every raised core name even when `position_pct` is below 2 x base and the raise is smaller. Faithful to the owner's private script (task-13 AC #1) but a latent off-by-a-little: with position_pct 8 and base 5 the budget shows 5 spent for a 3-point raise. Reported by the task-13 implementer and the verifier (PR #28).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_book.py::test_attack_topup_charges_the_actual_raise green
<!-- AC:END -->
