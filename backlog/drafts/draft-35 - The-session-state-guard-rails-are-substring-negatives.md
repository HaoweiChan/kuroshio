---
id: DRAFT-35
title: The session-state guard rails are substring negatives
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T50
  - 'PR #9 R14 (reviewer note 2)'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
the tests that keep PR #9's R6/R9 fix honest assert `"closed at" not in ...` and `"still-open" not in ...`, so a differently-worded state claim slips straight through: `f"at {price:.2f} ({asof} session), a finished close"` leaves the suite at 149 passed. The guard is against two spellings, not against the class of claim.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a positive full-phrase equality on the price clause of `card.reason`, so any added adjective goes red rather than only the two spellings that were shipped.
<!-- AC:END -->
