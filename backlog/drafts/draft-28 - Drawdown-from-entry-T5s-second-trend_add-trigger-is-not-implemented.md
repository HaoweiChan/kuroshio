---
id: DRAFT-28
title: 'Drawdown-from-entry, T5''s second trend_add trigger, is not implemented'
status: Superseded
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
superseded_by: TASK-11
references:
  - TASK-11
  - TODO.md T41
  - 'PR #9 R4'
priority: medium
---

## Resolution

Superseded by TASK-11. The open question — whether a `trend_add` should have an ALERT of its own below the DECIDE card — is answered by the ratchet: a `trend_add` at or below its trailed stop is alerted on the break, and the stop is the drawdown trigger.

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T5's spec reads "trend_add alerts on trend break (close < MA50 or ATR trail) **and** drawdown-from-entry". Only the MA break ships: engine.py:143 `if price >= ma: continue` is the sole trigger, and the drawdown figure is interpolated into a reason string that is only built after the MA test already fired. A trend_add at entry 200, price 130, MA50 120 — a deep loss still above its trend — produces no card at all. T5 deferred it because the threshold belongs to T6's forced-decision card with its own IPS key; recorded here so the gap is a numbered deferral rather than a code comment.

Depends (TODO.md ids): T6

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the drawdown trigger ships with a threshold owned by T6's IPS key; until then a trend_add at any loss above its MA50 is silent, and that is stated where the monitoring rules are documented. Update (T6 shipped): `caps.max_adverse_excursion_pct` exists and reads no setup_type, so that same trend_add now gets a DECIDE card — it is no longer silent, and T41 needs no second key. What is left is whether the *trend_add ALERT* should also fire on drawdown, i.e. whether one position deserves both cards at a threshold it already decided on.
<!-- AC:END -->
