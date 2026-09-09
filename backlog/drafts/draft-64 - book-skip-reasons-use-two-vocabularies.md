---
id: DRAFT-64
title: 'book skip reasons use two vocabularies (below cut vs below the attack floor)'
status: Draft
assignee: []
created_date: '2026-09-09'
labels:
  - debt
dependencies: []
references:
  - PR #35 (TASK-19)
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/book.py` `build_book`: a floor-skipped overflow name is appended to `skipped` inside the loop as "below the attack floor (<rating>)", while the post-loop sweep labels leftover names "<rating> (below cut)". Accounting is intact (each name lands once), but two skip-reason spellings for the same table make `alloc.md` / `needs_research.json` (TASK-15) consumers pattern-match two phrasings. Reported by the TASK-19 implementer; out of that task's three ACs.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_skip_reasons_share_one_vocabulary green
<!-- AC:END -->
