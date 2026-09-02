---
id: DRAFT-44
title: Two exotic decimal edges in _past_threshold
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T61
  - 'PR #10 R9 (reviewer notes)'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
two survivors of the round-3 rewrite, neither reachable from the shipped path today. (a) Setting the decimal context to `prec=6` inside `_past_threshold` leaves the suite at 184 passed — the 28-digit default is the only thing holding the product exact for entries above ~1e4, and `getcontext().prec` is process-global and mutable by any other library in the process. (b) A NaN price now raises `decimal.InvalidOperation` from the `<=` (decimal ordering signals on NaN) where the old float compare silently emitted a card reading `nan%`; unreachable because `signals.monitor_inputs` filters with `pd.notna` and a NaN entry_price is caught by `_entry_price`'s `> 0`.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the comparison runs in a `localcontext()` with an explicit precision, and a NaN price is refused the way a non-positive entry_price is; one case each.
<!-- AC:END -->
