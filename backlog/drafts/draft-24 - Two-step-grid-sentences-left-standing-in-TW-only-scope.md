---
id: DRAFT-24
title: Two step-grid sentences left standing in TW-only scope
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T36
  - 'PR #6 R20 (reviewer note)'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
a repo-wide grep after round 6 leaves exactly two step-grid claims: tw.py:33-38 (already T35) and the name plus docstring of `tests/test_cli.py::test_propose_refuses_when_the_hurdle_cannot_reject_anything`, which still say "clears the hurdle by construction and the gate cannot reject anything". That test is TW-only (`--market tw`, degraded 1/3 grid), so the claim is true in its scope, but it is the same sentence T35 is about and reads as a general law to the next reader.

Depends (TODO.md ids): T35

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 folded into T35's fix — both sites either scope the claim to equal surviving weights or stop asserting it.
<!-- AC:END -->
