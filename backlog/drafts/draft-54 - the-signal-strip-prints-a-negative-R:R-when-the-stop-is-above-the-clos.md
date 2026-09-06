---
id: DRAFT-54
title: 'the signal strip prints a negative R:R when the stop is above the close'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #30
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_rr` computes (target − close) / (close − stop) and returns a negative number when stop > close (a report whose stop was written above the last close), rendered as e.g. -2.0. Same arithmetic as task-13's alloc table. Verifier note on PR #30. Render n/a (or flag it) when the stop is not below the close.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_site.py::test_rr_is_na_when_stop_is_above_close green
<!-- AC:END -->
