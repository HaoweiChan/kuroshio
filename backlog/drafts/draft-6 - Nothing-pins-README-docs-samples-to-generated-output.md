---
id: DRAFT-6
title: Nothing pins README/docs samples to generated output
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T17
  - 'PR #4 R2'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
the drift PR #4 fixed can recur the next time card text changes — no test compares the README sample card or the docs/index.html `demo-data` reason strings against `to_markdown()` / `propose()`. The blocker is that the demo inputs currently live only inside the published HTML blob, so there is no fixture to drive a regeneration from.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the demo inputs live somewhere a test can read, and a test fails when the README sample or the docs demo reasons diverge from generated output.
<!-- AC:END -->
