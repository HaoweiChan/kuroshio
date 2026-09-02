---
id: DRAFT-9
title: Missing required holdings key still escapes as a bare TypeError
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T20
  - 'PR #5 R1'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T3 fixed the *unknown*-key TypeError out of `Holding(**item)` (cli.py:58) but not the *missing*-key one, and cli.py:249-251 catches only `ValueError`. Input `- {ticker: AAPL}` — a hand-edit that forgot `weight:`, an extremely realistic holdings.yml typo — produces `TypeError: Holding.__init__() missing 1 required positional argument: 'weight'` as a full traceback, exit code 1, not the exit-2 `error:` path the same function now provides for `entrey_price`. Out of T3's scope (its acceptance names unknown keys only), but it is the same line of code.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a holdings item missing `ticker` or `weight` exits 2 with a message naming the file, the offending entry, and the missing key; covered by a test alongside test_propose_exits_2_on_unknown_holdings_key.
<!-- AC:END -->
