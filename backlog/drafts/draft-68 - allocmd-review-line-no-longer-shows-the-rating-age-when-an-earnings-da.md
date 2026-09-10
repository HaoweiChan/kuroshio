---
id: DRAFT-68
title: 'alloc.md review line no longer shows the rating age when an earnings date is present'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #40 (TASK-15)
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since `render_alloc_md` renders the review block from `needs_research`, a held name inside the earnings window prints `(2026-01-05, earnings in 5 days)` where it used to print `(2026-01-05, 24d, earnings 2026-02-06)`: the rating age is no longer rendered anywhere for that row. Reported as a non-blocking note by the TASK-15 verifier. Either add the age back to the prose (the JSON reason stays single) or state that one reason per row is the design.

Probe: none — rendering change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case the review line for a name inside the earnings window shows both the age and the print date, or the docstring states one reason per row
<!-- AC:END -->
