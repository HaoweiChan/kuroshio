---
id: DRAFT-32
title: The alert card still calls the traded-session mean a 50-day moving average
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T47
  - 'PR #9 R13'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #9's R3 repair changed MA50 to the mean of each ticker's last 50 *traded* closes and corrected engine.py:159 to say "fewer than 50 traded sessions", but engine.py:169-170 and :175 still say "its 50-day moving average of {ma:.2f}", and README.md:69-71 still says "closes under its 50-day mean". After a halt those differ: a TW-shaped 82-row panel with a 31-session halt ending today yields an ma of 99.40 computed from 51 traded closes spanning ~115 calendar days, and the card calls it a 50-day moving average. signals.py's docstring and docs/ARCHITECTURE.md:167-169 already say "traded sessions"; the user-visible strings do not. Also fold in (PR #9 R14 note 3): docs/ARCHITECTURE.md:158-161 and README.md:69-71 still describe the rules as firing on "the close" ("ALERT when the close is under its 50-day mean", "when it closes at or below the invalidation price you recorded") while the card now deliberately refuses to call the print a close — the same claim one layer up, in the same two files.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the alert card, README and ARCHITECTURE wording match what the number is ("50-session" or "the last 50 traded closes") and stop calling the print a close, consistent with the coverage card. T44 still owns the staleness signal itself.
<!-- AC:END -->
