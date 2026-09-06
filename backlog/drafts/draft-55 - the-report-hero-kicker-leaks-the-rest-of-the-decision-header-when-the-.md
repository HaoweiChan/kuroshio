---
id: DRAFT-55
title: 'the report hero kicker leaks the rest of the decision header when the `·` separator is absent'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #30
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
kuroshio/site/render.py `_decision_meta` grabs the market with `\*\*Market:\*\*\s*([^·\n]+)`; a decision.md header written without the ` · ` separators puts everything after Market: into the hero kicker. Verifier note on PR #30. Stop at the next `**` field or whitespace run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_site.py::test_market_grab_stops_at_the_header_field green
<!-- AC:END -->
