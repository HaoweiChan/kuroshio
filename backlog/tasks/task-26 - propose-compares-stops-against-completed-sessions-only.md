---
id: TASK-26
title: 'propose compares stops against completed sessions only'
status: PR
assignee: []
created_date: '2026-10-14'
labels: []
dependencies: []
references:
  - DRAFT-33
  - TASK-20
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen 2026-10-09 01:24 Taipei (2026-10-08 13:24 ET, mid-NYSE-session): the actual-portfolio
`propose` pass fired `EXIT RVMD` because the "2026-10-08 session" price 185.43 was below the
187.00 stop. That number was yfinance's still-forming intraday bar; RVMD closed 188.12 that day
and never closed at or below 187 through 10-13. `core/book.py` `stopped_out` is close-based, so
the two rules disagreed about the same stop.

Change: each market profile (`core/screening/__init__.py`) carries its session close as
(timezone, HH:MM) — `us` America/New_York 16:00, `tw` Asia/Taipei 13:30. `_run_propose` drops
the panel's final row when that row is the market's today and the market's clock is before the
close, so every price `propose` reads (stop/EXIT, MA50, trail, scores) is a finished session.

Probe: `KUROSHIO_LEDGER_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips ~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/actual/holdings_us.yaml --market us --no-ledger` · budget $0 · reps 1 — during the NYSE session the cards' session label is the previous trading day; after 16:00 ET it is today.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 with the clock stubbed at 13:24 ET on a session whose partial bar is below a holding's invalidation price, `propose` emits no EXIT for it and reads the previous session; at 16:30 ET the same panel fires the EXIT — a test each.
- [ ] #2 a TW market read at 21:00 Taipei keeps today's bar; a panel whose last row is not the market's today is never trimmed — tests with a stubbed clock, never the local one.
<!-- AC:END -->
