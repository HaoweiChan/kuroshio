---
id: DRAFT-26
title: The ATR trail T5 was specced with is not computable
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T38
  - T5
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T5's spec says a trend_add alerts on "close < MA50 or ATR trail". Only the MA50 half shipped: `Panel` (kuroshio/types.py:15) carries `close`, `volume` and `institutional` and nothing else, so no true range — and therefore no ATR — is reachable from any provider's output today. Both providers (`providers/yf.py`, `providers/finmind.py`) fetch OHLCV and keep close/volume; the fields exist upstream, they are dropped at the boundary. An ATR trail is the better trend-break signal for a volatile name, where a fixed MA50 either whipsaws or lags depending on the tape, so this is a real gap, not a stylistic one — it is just a data-model change (Panel gains high/low, both providers populate it, backtest/screening keep working) that exceeds a monitoring-rules task.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `Panel` carries high/low from both providers, and the trend_add rule alerts on either the MA50 break or an ATR-multiple trail from the running high, with a test per trigger. Until then `core/allocator/engine.py` step 3 says MA50 only, in a `ponytail:` comment naming this task.
<!-- AC:END -->
