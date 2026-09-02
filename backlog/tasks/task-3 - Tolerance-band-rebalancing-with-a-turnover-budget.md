---
id: TASK-3
title: Tolerance-band rebalancing with a turnover budget
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T9
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
replace the binary hard-cap TRIM with Daryanani-style relative bands: flag when a position drifts outside ±band_rel (default 20%) of its target weight, propose trading back to the band edge (not to target), ranked by drift severity, subject to the existing max_swaps_per_week style turnover budget.

Depends (TODO.md ids): T7

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 position at 12.5% vs 10% target with band 20% yields a card whose proposed weight is the band edge (12%); position at 11% yields none; band and budget read from IPS.
<!-- AC:END -->
