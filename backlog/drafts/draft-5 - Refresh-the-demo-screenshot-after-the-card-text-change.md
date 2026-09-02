---
id: DRAFT-5
title: Refresh the demo screenshot after the card-text change
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T16
  - 'PR #4 R2'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #4 regenerated the README sample card and the five `demo-data` reason strings in docs/index.html from a live `propose()` run, but docs/screenshot-proposals.png still renders the pre-T2 wording ("Estimated round-trip friction: 0.020%."). It was left stale deliberately — it is the only member of that artifact set that cannot be regenerated from code. The cards themselves are unchanged; only the reason text drifted.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/screenshot-proposals.png shows the current card text, and the README alt text and surrounding prose still describe what the image shows.
<!-- AC:END -->
