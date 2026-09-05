---
id: DRAFT-50
title: 'propose has no --no-ledger flag, so every stop move writes to the ledger with no opt-out'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/cli.py` `propose` appends ratchet rows to `stops.jsonl` on every run; `screen` and `research` have `--no-ledger`, `propose` does not, so a dry run or a probe cannot avoid writing state.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_propose_no_ledger_skips_the_stop_ledger green
<!-- AC:END -->
