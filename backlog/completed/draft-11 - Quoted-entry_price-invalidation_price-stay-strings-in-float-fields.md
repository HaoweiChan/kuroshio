---
id: DRAFT-11
title: Quoted entry_price/invalidation_price stay strings in float fields
status: Done
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

## Resolution

Closed by TASK-15. `_holdings_from_yaml` coerces `entry_price`/`invalidation_price` to
`float` (numeric strings included) or raises a `ValueError` naming the ticker and field
for a value that isn't a number. Covered by `test_holdings_from_yaml_coerces_quoted_prices`
and `test_holdings_from_yaml_rejects_non_numeric_entry_price` (tests/test_cli.py).

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:55-57 coerces dates but not the two numeric entry fields. Input `- {ticker: A, weight: 0.1, entry_price: "180.5", invalidation_price: "150"}` yields `Holding(entry_price='180.5', invalidation_price='150')` — quoting prices is a common YAML habit, and T7 (percent-risk cap from the entry−invalidation distance) will do arithmetic on these.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 numeric-string `entry_price`/`invalidation_price` either coerce to float or raise a message naming the ticker and the key; one test case.
<!-- AC:END -->

## Scheduled

Rolled into TASK-15 (input type validation for holdings.yml and candidates.yml) — do not
fix separately; that task closes all seven together and moves this file on merge.
