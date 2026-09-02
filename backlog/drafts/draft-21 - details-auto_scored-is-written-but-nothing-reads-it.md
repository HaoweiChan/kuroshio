---
id: DRAFT-21
title: 'details["auto_scored"] is written but nothing reads it'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T32
  - 'PR #6 R15'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
core/allocator/engine.py:150 records `"auto_scored": auto` on the card, but `details` is referenced nowhere in `to_markdown` (types.py:69) or in integrations/discord.py, and no test asserts it — mutating the line to `"auto_scored": []` leaves the suite at 128 passed. It also drops the pool size the prose disclosure carries, so it is not even a machine-readable copy of the sentence.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 either the field is dropped (nothing reads it) or one allocator test asserts it, e.g. `cards[0].details["auto_scored"] == ["1102", "1101"]`, so the mutation goes red.
<!-- AC:END -->
