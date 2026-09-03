---
id: DRAFT-45
title: Example IPS presets all inherit the same 1% risk_budget_pct
status: Draft
assignee: []
labels:
  - debt
dependencies: []
references:
  - 'PR #13 (implementer-reported)'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`caps.risk_budget_pct` landed with a default of 1 and none of the three shipped presets set it, so conservative, balanced and aggressive all risk the same 1% of NAV per position while their `position_pct` differs 5/10/15. The percent-risk cap therefore binds identically across three profiles that are supposed to size differently. Repro: `parse_ips(examples/ips-conservative.md).caps.risk_budget_pct == parse_ips(examples/ips-aggressive.md).caps.risk_budget_pct == 1`, while their `position_pct` are 5 and 15.

Probe: none — library/CLI with no deployed surface
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `test_presets_set_their_own_risk_budget` green: each example IPS sets a `risk_budget_pct` consistent with its `position_pct`, and the case fails if two presets share one.
<!-- AC:END -->
