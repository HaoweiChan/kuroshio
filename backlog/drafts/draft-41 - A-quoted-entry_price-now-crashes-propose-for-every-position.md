---
id: DRAFT-41
title: A quoted entry_price now crashes propose for every position
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T56
  - 'PR #10 R5'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T6's `_entry_price` gate evaluates `h.entry_price > 0` for every holding, so `entry_price: "100.0"` in holdings.yml raises a bare `TypeError: '>' not supported between instances of 'str' and 'int'`. Before T6 a position with no monitored setup_type was skipped by step 3 entirely and never reached the comparison, so this widens an existing crash surface. `_holdings_from_yaml` (cli.py:44-64) validates key names and setup_type but never field types — the same gap T22 records for the coercion side.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 either the holdings loader rejects a non-numeric entry_price with a message naming the ticker and key (folding in T22), or `_entry_price` treats a non-number as absent; one test on a quoted-price holdings file.
<!-- AC:END -->
