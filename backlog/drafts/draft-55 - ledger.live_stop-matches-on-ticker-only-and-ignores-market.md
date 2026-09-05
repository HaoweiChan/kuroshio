---
id: DRAFT-55
title: 'ledger.live_stop matches on ticker only and ignores market'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/ledger.py` `live_stop` keys stop rows by ticker, so the same symbol held in a `us` and a `tw` book would share one stop history; rows already carry `market`.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_live_stop_is_keyed_by_market_and_ticker green
<!-- AC:END -->
