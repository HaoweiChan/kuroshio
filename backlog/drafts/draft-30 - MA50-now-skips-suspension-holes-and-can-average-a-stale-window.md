---
id: DRAFT-30
title: MA50 now skips suspension holes and can average a stale window
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T44
  - 'PR #9 R3'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
the R3 fix in `core/allocator/signals.py:monitor_inputs` averages each ticker's last `MA_TREND` *traded* closes instead of the last `MA_TREND` rows, so a one-day suspension no longer voids MA50. The trade-off it buys: holes are skipped, not counted, so a ticker halted for months averages 50 closes that may reach far further back than 50 sessions, and nothing on the card says the number is stale. The panel's own `lookback_days` bounds how far back it can reach, which is why this is P3 and not higher. A staleness signal needs a per-ticker "sessions spanned" number, which is the same shape as the high/low data the ATR trail needs (T38).

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 either a trend_add whose MA50 spans materially more than `MA_TREND` calendar sessions is named on the coverage card with that reason, or the tolerance is bounded (skip at most N holes) — pinned by a test with a long gap inside the window.
<!-- AC:END -->
