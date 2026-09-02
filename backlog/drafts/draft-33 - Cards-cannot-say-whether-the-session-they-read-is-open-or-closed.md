---
id: DRAFT-33
title: Cards cannot say whether the session they read is open or closed
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T48
  - 'PR #9 R6'
  - R9
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #9's round-2 repair dropped the open/closed claim from `_price_phrase` (engine.py) — the card now reads "at 60.00 (2026-08-27 session)" and asserts nothing about session state, because deciding it needs the market's close time in the market's own timezone and no profile carries one. The local date is not that oracle in either direction: 01:00 Taipei with `--market us` is mid-NYSE-session under yesterday's local date, and 21:00 Taipei with `--market tw` is 7.5h past a close on today's. Saying "still-open"/"closed" honestly means encoding (tz, open, close) per market profile in `core/screening/__init__.py` and comparing `datetime.now(tz)` against the `asof` session's close — a data-model change T5 deliberately did not make. Only do this if a user actually wants the adjective; the session label alone is not wrong without it.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 profiles carry a session calendar; `_price_phrase` takes the market and says open/closed from it; tests cover a US market read from a UTC+8 clock at 01:00 and a TW market read at 21:00, with the clock stubbed, not the local one.
<!-- AC:END -->
