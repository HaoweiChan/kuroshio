---
id: DRAFT-20
title: Drop notice misattributes a provider no-data miss as a gate failure
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T31
  - 'PR #6 R12'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:295 picks the reason with `why = "did not pass the Stage-1 gate" if ranked else "could not be auto-scored"` — keyed off whether the *pool* was ranked, not off why *this* name is missing. A candidate the provider returned no data for (`- {ticker: "9999", verdict: buy}`, typo or delisted) is reported as `... did not pass the Stage-1 gate: 9999`. Mirror case: a holding `9999` gets `h.score = ranked.get(...) -> None` at cli.py:283 and is excluded from ranking with no notice at all, against the same block's stated "reported rather than dropped in silence" principle.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the reason is split per name (`not in ranked` -> "no price data returned by the provider", `not in eligible` -> "did not pass the Stage-1 gate"), unscorable holdings are reported on stderr too, and a test asserts the no-data wording for a ticker the stub panel does not contain.
<!-- AC:END -->
