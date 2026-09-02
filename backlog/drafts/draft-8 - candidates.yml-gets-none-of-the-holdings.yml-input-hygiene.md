---
id: DRAFT-8
title: candidates.yml gets none of the holdings.yml input hygiene
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T19
  - T3
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T3 gave `_holdings_from_yaml` (cli.py) unknown-key detection and a clear `error:`/exit-2 path in `cmd_propose`. PR #6 R4 gave `_candidates_from_yaml` the same unknown-key check and routed it through the same exit-2 path; what is left is the *missing*-key half — bare `item["ticker"]` still raises a context-free `KeyError` traceback out of the CLI. `_load_yaml` also assumes a top-level list: a file written as a YAML mapping iterates as strings and dies on `item.get`.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a candidates.yml with a missing/misspelled key exits 2 with a message naming the file and the key; a non-list top-level document is rejected with a clear message — this covers `_holdings_from_yaml` too, whose `item.get` is the line that raises `AttributeError` on a non-mapping entry (`- AAPL`); covered by tests alongside the T3 holdings cases.
<!-- AC:END -->
