---
id: DRAFT-71
title: 'a rating with surrounding whitespace passes the ledger writer but is ignored by the veto'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #42 (TASK-16)
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/mcp_server.py` validates `rating.strip().lower()` but writes the raw string; `_rank` in `kuroshio/core/ips/schema.py` lowercases without stripping, so a `' Sell '` row is accepted and then silently ignored by both `book`'s VETO check and `propose`'s new rating DECIDE step. Normalise once at the ledger boundary (write the stripped, canonical-case rating). Reported as a non-blocking LOW by the TASK-16 verifier; pre-existing.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case a rating written as ' sell ' is read back as Sell by book and propose alike
<!-- AC:END -->
