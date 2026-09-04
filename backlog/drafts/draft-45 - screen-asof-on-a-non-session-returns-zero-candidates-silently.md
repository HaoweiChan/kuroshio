---
id: DRAFT-45
title: '`screen --asof` on a non-session returns zero candidates silently'
status: To Do
assignee: []
created_date: '2026-09-04'
labels: []
dependencies: []
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio screen --market us --asof 2026-08-01` (a Saturday) prints `candidates=0` and, with the ledger on, `ledger: 0 rows`: every screener's `_screen_or_score` returns `[]` when `asof` is not in the panel index. Seen 2026-09-04 while smoke-testing the ledger (PR #16). Either resolve to the previous session and say so on the table header, or exit 2 naming the date as a non-session — never an empty table that looks like "nothing passed the gate". `core/ledger._positional_index` already resolves a non-session to the next open; the screeners and `_print_screen_table` should agree on one rule.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `screen --asof <Saturday>` either screens the previous session and prints that date, or exits 2 with a message naming the date; a test pins the chosen behaviour for `us`, `us-leadership` and `tw`.
<!-- AC:END -->
