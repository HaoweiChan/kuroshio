---
id: DRAFT-51
title: '`kuroshio book --provider` price columns (MA50, book vol) have no test'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #28
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`cli._price_columns` fetches a 90-day panel to fill the vs-MA50 column and the trailing book volatility; it is off by default and wrapped in try/except, so a broken fetch or a wrong column silently shows n/a. No provider fake exists in the suite. Verifier note on PR #28. A fake provider returning a fixed panel and one case asserting both columns closes it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_cli_book.py::test_provider_price_columns_from_a_fake_panel green
<!-- AC:END -->
