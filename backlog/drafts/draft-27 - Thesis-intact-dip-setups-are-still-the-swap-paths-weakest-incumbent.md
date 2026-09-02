---
id: DRAFT-27
title: Thesis-intact dip setups are still the swap path's weakest incumbent
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T39
  - T5
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T5 fixed the alerting axis, not the ranking one, and its own opening sentence is about the ranking one. `core/allocator/engine.py` step 4 picks `incumbent = min(pool, key=lambda h: h.score)`, where `score` is the screener's momentum composite: `screening/us.py:135` computes `mom_raw = (c / ma50 - 1) + (c / ma200 - 1)` — literally MA distance — at the largest single factor weight (0.333 of four), and TW's momentum half is close/MA20 + close/MA60 + volume multiple. A `value_dip` bought *because* it is far under its MAs therefore scores lowest by construction and is the name proposed for sale, even while its invalidation price is untouched and T5's monitoring is deliberately silent about it. The two halves now disagree: monitoring says "thesis intact", the SWAP card says "sell this one". T5's acceptance covers alerts only, so this was logged rather than fixed.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a fixture with one thesis-intact `value_dip` (score lowest, price above `invalidation_price`) and one `trend_add` shows the swap path not choosing the value_dip as the sell side — whether by excluding intact dip setups from the incumbent pool, ranking on something other than the momentum score, or requiring the setup's own invalidation before a dip position may be swapped out. Whichever way, the reason string must say why that incumbent was picked, and the existing `test_theme_breach_alert_and_same_theme_swap_constraint` style coverage must still pass for holdings with no setup_type.
<!-- AC:END -->
