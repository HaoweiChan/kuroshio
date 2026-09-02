---
id: DRAFT-16
title: Candidate.final_score is annotated float but now holds None
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T28
  - 'PR #6 R8'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
types.py:29 declares `final_score: float`; cli.py:75 now stores `item.get("final_score")`, i.e. None, and `propose()` in core/allocator/engine.py sorts challengers by `final_score`, which would raise TypeError if a None ever reached it. Not reachable through `cmd_propose` today (the `any(... is None)` guard routes to `_score_missing`, which filters), but `_candidates_from_yaml` is called directly in tests and is now a documented-optional-field parser with a lying type.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `final_score: float | None` on the dataclass, or `_candidates_from_yaml` returns only scored candidates.
<!-- AC:END -->
