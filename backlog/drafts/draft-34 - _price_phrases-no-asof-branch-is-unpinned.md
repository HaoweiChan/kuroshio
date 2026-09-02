---
id: DRAFT-34
title: _price_phrase's no-asof branch is unpinned
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T49
  - 'PR #9 R14 (reviewer note 1)'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
engine.py:33-34's `asof is None` branch is guarded by nothing — mutating it to `return f"it closed at {price:.2f} in the still-open session"` leaves the suite at 149 passed. Not user-visible today: cli.py:357-365 leaves `prices={}` whenever `asof` stays None, so the branch is unreachable through the CLI. But PR #9's round-2 repair changed its text, and a library caller passing `prices=` without `asof=` would get it.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one case asserts the no-asof wording; the mutation goes red.
<!-- AC:END -->
