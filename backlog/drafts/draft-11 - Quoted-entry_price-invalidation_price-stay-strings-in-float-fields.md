---
id: DRAFT-11
title: Quoted entry_price/invalidation_price stay strings in float fields
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T22
  - 'PR #5 R4'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:55-57 coerces dates but not the two numeric entry fields. Input `- {ticker: A, weight: 0.1, entry_price: "180.5", invalidation_price: "150"}` yields `Holding(entry_price='180.5', invalidation_price='150')` — quoting prices is a common YAML habit, and T7 (percent-risk cap from the entry−invalidation distance) will do arithmetic on these.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 numeric-string `entry_price`/`invalidation_price` either coerce to float or raise a message naming the ticker and the key; one test case.
<!-- AC:END -->
