---
id: DRAFT-49
title: '`kuroshio book` has no --cash option, so a partial positions export understates cash'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #28
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Cash on the allocation page is derived as nav minus the sum of market values in the positions table (core/book.py, alloc). A broker export that omits an account or a money-market line understates cash and overstates what is left after the book. Found while implementing task-13 (PR #28). A `--cash N` option that overrides the derived figure, with the alloc page saying which one it used, closes it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_book.py::test_cash_option_overrides_the_derived_figure green
<!-- AC:END -->
