---
id: DRAFT-52
title: 'site report cards read the PM decision with regexes and show n/a everywhere on any other format'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #28
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
kuroshio/site/render.py `_decision_meta` parses `5_portfolio/decision.md` with regexes for **Rating**, **Stop Loss**, **Price Target**, **Last close**; a decision written in another language or shape yields {} and the report card shows n/a in every cell with no warning. Implementer note on PR #28. Either write the rating/levels as a small JSON sidecar when the report is produced (the ledger already has them) or warn per report on the index page.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_site.py::test_report_card_reads_levels_from_the_ledger_sidecar green
<!-- AC:END -->
