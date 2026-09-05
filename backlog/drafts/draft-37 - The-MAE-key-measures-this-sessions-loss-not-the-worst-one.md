---
id: DRAFT-37
title: 'The MAE key measures this session''s loss, not the worst one'
status: Superseded
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
superseded_by: TASK-11
references:
  - TASK-11
  - TODO.md T52
  - T6
priority: medium
---

## Resolution

Superseded by TASK-11. `caps.max_adverse_excursion_pct` now compares the minimum close since `entry_date` (`signals.trail_inputs`), so a position that fell to -25% and recovered to -5% still gets its DECIDE card, and the card names the low it measured.

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`caps.max_adverse_excursion_pct` is compared against the latest session price (`core/allocator/engine.py` step 3b), so a position that fell to -25% from entry and recovered to -5% is never decided on, though its max adverse excursion was -25%. Latest price vs entry equals MAE only for someone who runs `propose` on the day of the low; a weekly runner silently misses the decisions the discipline exists to force. The true number needs the minimum close since `entry_date` — panel history sliced per position, the same data-model shape T38/T44 already need. The card text says what it measured ("is -20.0% from your entry price of ..."); it is the key's name that promises more.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 either the threshold is compared against the low since `entry_date`, or the key and docs stop calling it the max adverse excursion; a test with a recovered position pins whichever is intended.
<!-- AC:END -->
