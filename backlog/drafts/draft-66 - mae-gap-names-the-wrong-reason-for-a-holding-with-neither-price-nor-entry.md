---
id: DRAFT-66
title: 'the mae gap names "no price" for a holding that has neither a price nor an entry_price'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #39 (TASK-20)
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/allocator/engine.py` MAE step checks `price is None` before `entry_price is None`, so a holding with neither gets "no price for this session" in `mae_gap` rather than "no entry_price". Cosmetic since TASK-20 (the price clause is now suppressed on the coverage line for names on the missing-price ALERT), but the reason order still hides the entry gap on a fetched run. Also `tests/test_cli.py` around the vol-target case carries a stale comment claiming `ips-balanced.md` sets `caps.book_vol_target_pct`. Reported by the TASK-20 implementer; outside its ACs.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_mae_gap_names_the_missing_entry_before_the_missing_price green
<!-- AC:END -->
