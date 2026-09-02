---
id: DRAFT-2
title: Unrecognized challenger verdicts fail silently
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T12
  - 'PR #3 R3'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_rank` matches exactly after `.lower()` with no `.strip()`, so `verdict_at_least(" hold ", "neutral")` is False while `"hold"` is True — a quoted trailing space in candidates.yml (plausible from a pasted research report) drops the challenger. The allocator compounds it: core/allocator/engine.py:102 `continue`s with no ALERT when the floor is not cleared, so an unparseable verdict produces zero output rather than a diagnostic. This is the same silent-False class of bug T1 was written to close, one layer out.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a challenger whose verdict string is unrecognized (not merely low-rated) surfaces a visible ALERT card rather than vanishing; whitespace-padded verdicts rank correctly, covered by a test case.
<!-- AC:END -->
