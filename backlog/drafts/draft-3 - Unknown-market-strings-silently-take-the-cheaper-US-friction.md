---
id: DRAFT-3
title: Unknown market strings silently take the cheaper US friction
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T14
  - 'PR #4 R3'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
core/allocator/engine.py:94 picks friction with `"tw_roundtrip_pct" if market.lower() == "tw" else "us_roundtrip_pct"`. Since T2 that choice is a real gate, not a caption, so `' tw'`, `'twse'`, `'jp'`, `'hk'` and `''` all silently gate at the 0.02% US number and the card cites `friction.us_roundtrip_pct` for a non-US trade. `propose()` is a documented public entry point (docs/ARCHITECTURE.md:144) and docs/adding-a-market.md walks contributors through adding a `jp` market; the CLI's `choices=["us","tw"]` (cli.py:373) is the only thing currently containing it.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 an unrecognized market normalizes or raises explicitly rather than defaulting to the cheapest friction, covered by a test using a market string that is neither 'us' nor 'tw'.
<!-- AC:END -->
