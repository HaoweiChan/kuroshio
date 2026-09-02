---
id: DRAFT-29
title: Both thesis comparison boundaries are unpinned
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T42
  - 'PR #9 R7'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
engine.py:152 `if price > h.invalidation_price: continue` and engine.py:143 `if price >= ma: continue`. Mutating the first to `>=` and the second to `>` each leave the suite green, while README.md:70 promises a dip is "alerted only when it closes at or below the invalidation price you recorded" — so the documented boundary is unpinned. (Mutating MONITORED_SETUPS or removing entry_price from the reason string IS caught, so the core dispatch itself is properly pinned.)

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one case with `price == invalidation_price` asserting the alert fires and one with `price == ma50` asserting whichever the docs say; both mutations go red.
<!-- AC:END -->
