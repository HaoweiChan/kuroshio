---
id: DRAFT-10
title: 'entry_date is coerced but never validated, yet documented as ISO'
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T21
  - 'PR #5 R3'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:55-57 coerces `entry_date` with `str()` and never validates it, while types.py:49 (`entry_date: str | None = None  # ISO date`) and docs/ARCHITECTURE.md:68 call it an ISO date. `entry_date: 2025-01-15 10:30:00` stores `'2025-01-15 10:30:00'` (not an ISO date, and not ISO-8601 datetime either — no `T`); `entry_date: not-a-date` stores `'not-a-date'`. T5/T6 (drawdown-from-entry, MAE cards) are specified to consume this field.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 either the comment/doc drop the ISO claim, or the loader rejects a value `datetime.date.fromisoformat` cannot parse with a message naming the ticker and the value; one test case.
<!-- AC:END -->
