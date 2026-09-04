---
id: TASK-1
title: Position sizing engine
status: Done
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T7
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`caps.position_pct` is parsed, validated, documented — and read by nothing; TRIM/SWAP cards carry no target weight. Compute a target weight per proposal as the min of three caps, and name the binding cap on the card: (a) position_pct base; (b) percent-risk: risk_budget_pct × NAV / (entry − invalidation), when both prices exist; (c) inverse-vol parity toward a portfolio vol target. Start with (a)+(b); (c) may land as a follow-up if provider vol data is not ready.

Depends (TODO.md ids): T3

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 TRIM cards state a numeric target weight; a swap proposal for a position with entry/invalidation prices shows the percent-risk cap binding when it is the min; unit tests cover each cap being the binding one.
<!-- AC:END -->
