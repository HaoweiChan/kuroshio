---
id: DRAFT-46
title: DECIDE cards carry no target weight for their add option
status: Draft
assignee: []
labels:
  - debt
dependencies: []
references:
  - 'PR #13 (implementer-reported)'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
"Add to it per the plan you opened it with" is one of the DECIDE card's three options, and a DECIDE only fires on a position that has an entry price — exactly the input `target_weight` needs — yet the card states no number, unlike its TRIM sibling. The user is told to add without being told to what. Repro: `propose([Holding(ticker="X", weight=0.05, entry_price=100.0, invalidation_price=90.0, setup_type="value_dip")], [], ips, "us", prices={"X": 84.0})` yields a DECIDE card whose `details` has no `target_weight` key.

Probe: none — library/CLI with no deployed surface
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `test_decide_card_sizes_its_add_option` green: the DECIDE card for a position with entry and invalidation prices states a numeric target weight and names its binding cap, matching what TRIM would say for the same position.
<!-- AC:END -->
