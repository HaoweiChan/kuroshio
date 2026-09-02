---
id: DRAFT-19
title: tw.MIN_RANK_WEIGHT's comment states a market-specific law as a general one
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T35
  - 'PR #6 R19'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/core/screening/tw.py:35` says two names in a pool of n "cannot differ by less than MIN_RANK_WEIGHT / (n - 1) without tying". That is true for TW, whose degraded weights are equal (1/3, 1/3, 1/3), and false in general — US degraded is 0.625/0.375 and reaches smaller gaps (R19). Left as-is because it is correct where it is written, but it is the sentence someone will copy when adding a market, which is exactly how R19 got in.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the comment scopes the claim to TW's equal degraded weights, or drops the arithmetic and points at `cli.py:_score_missing` like the US one now does.
<!-- AC:END -->
