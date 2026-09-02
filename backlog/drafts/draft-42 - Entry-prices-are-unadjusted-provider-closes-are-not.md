---
id: DRAFT-42
title: 'Entry prices are unadjusted, provider closes are not'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T57
  - 'PR #10 R7 (reviewer note)'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
providers/yf.py:52 fetches with `auto_adjust=True`, so every US price reaching `propose` is a split/dividend-adjusted close, while `entry_price` is hand-typed into holdings.yml and is not adjusted. Every rule that compares the two — T5's MA50 break and invalidation breach, T6's MAE trigger and its printed drawdown — is skewed across any split or dividend since entry, silently and in a direction nobody is told about. A 2:1 split alone puts a healthy position at -50% from entry. Adjusted closes are also not on the cent grid, so the `ponytail:` comment at the MAE comparison ("US and TW both quote in cents") is not true of what this code actually receives; TW is safe on the cent question specifically (TWSE tick sizes are all multiples of 0.01), so the tick-size upgrade path that comment names does not address the adjusted-close half.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 entry-relative rules compare like with like — either entry prices are adjusted onto the same basis as the panel, or the position is flagged when a corporate action has occurred since entry_date rather than silently mis-measured; a test with a split between entry_date and the panel's last session pins the chosen behaviour.
<!-- AC:END -->
