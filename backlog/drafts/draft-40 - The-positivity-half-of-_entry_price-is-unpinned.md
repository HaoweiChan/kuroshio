---
id: DRAFT-40
title: The positivity half of _entry_price is unpinned
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T55
  - 'PR #10 R3'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
engine.py:44 `return h.entry_price if h.entry_price and h.entry_price > 0 else None` and docs/ARCHITECTURE.md 3b state that a zero or negative entry_price is treated as absent, but only 0.0 is tested. Mutating the line to drop `and h.entry_price > 0` leaves the suite at 161 passed while `entry_price=-5.0` then produces no DECIDE, vanishes from the coverage card entirely (it reads as fully watched), and prints "entry price -5.00, now -1100.0% from entry" on the thesis card.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a case with `entry_price=-5.0` asserts no DECIDE, the coverage card naming it, and `details['entry_price'] is None` on the thesis card; the mutation goes red.
<!-- AC:END -->
