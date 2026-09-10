---
id: DRAFT-69
title: 'kuroshio book and the MCP propose tool still append stop moves with no opt-out'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #41 (TASK-17)
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio book` calls `_run_propose` in-process and the MCP `propose` tool takes the ledger default, so a book preview or a session-mode propose still writes `stops.jsonl` rows; only the CLI `propose --no-ledger` skips the append. In the daily cron this is what the desk relies on for real positions (the ACTUAL pass), so the default must stay; but `book` should pass `log_ledger=False` when run with a dry-run style flag, and the MCP tool should expose the same switch. Reported as non-blocking notes by the TASK-17 verifier.

Probe: none — flag plumbing, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `kuroshio book --no-ledger` and the MCP propose tool's `no_ledger` argument leave stops.jsonl byte-identical
<!-- AC:END -->
