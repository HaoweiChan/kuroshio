---
id: DRAFT-56
title: 'a rating spelled outside the known set gets no tone colour on the report page'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #30
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The hero and verdict card colour the rating only when it matches RATINGS exactly (Buy, Overweight, Hold, Underweight, Sell); `BUY` or `buy` renders in --fg. The ledger normalises ratings on write, so this only bites hand-written decision files. Verifier note on PR #30. Normalise case before the lookup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_site.py::test_unknown_rating_case_still_gets_a_tone green
<!-- AC:END -->
