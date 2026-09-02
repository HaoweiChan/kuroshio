---
id: DRAFT-22
title: Disclosed pool size is unpinned when the provider returns fewer names
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T33
  - 'PR #6 R16'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:275,284 record `len(ranked)` and engine.py:129 prints `auto_scored[auto[0]]`. Mutating those cli lines to `len(names)` leaves 128 passed, because every stub panel in tests/test_cli.py contains every requested ticker; the two numbers diverge only when a provider returns no data for a listed ticker (the T31 case), where the card then overstates how many names it ranked against. The card also reports only the first auto-filled ticker's pool size.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one case with a stub panel missing a listed ticker asserts the disclosure reports the number actually ranked, not the number listed.
<!-- AC:END -->
