---
id: DRAFT-31
title: monitor_inputs' history threshold has an unpinned boundary
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T46
  - 'PR #9 R12'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
signals.py:46 `if len(traded) >= MA_TREND:`. The fixtures use 60 traded and 40 traded sessions; nothing sits at exactly 50, so mutating `>=` to `>` leaves the suite at 145 passed and a ticker with exactly 50 traded sessions silently flips between monitored and "fewer than 50 traded sessions". T42 covers the two comparisons in engine.py, not this one — it is new code from PR #9's round-1 repair.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a fixture column with exactly MA_TREND traded sessions asserts it is monitored; the mutation goes red.
<!-- AC:END -->
