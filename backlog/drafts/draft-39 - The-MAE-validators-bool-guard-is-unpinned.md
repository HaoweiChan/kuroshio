---
id: DRAFT-39
title: The MAE validator's bool guard is unpinned
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T54
  - 'PR #10 R2'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
parser.py:123 `if isinstance(mae, bool) or not isinstance(mae, (int, float)):` is correct but guarded by no test — tests/test_ips.py::test_validate_catches_a_mae_threshold_with_the_wrong_sign_or_type exercises None, "-15", abc and .nan, never a boolean. Removing the bool clause leaves the suite at 161 passed, and `max_adverse_excursion_pct: true` then reports the *range* message instead of the type message (True == 1) — the exact T18 shape the validator's own docstring says it avoids.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a case asserting `true` (and `false`) produces the "must be a number, not bool" message and not the range message; the guard-removal mutation goes red.
<!-- AC:END -->
