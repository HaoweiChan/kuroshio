---
id: DRAFT-65
title: 'the cli research path writes source/model as null in the ledger row and decision.json'
status: Draft
assignee: []
created_date: '2026-09-09'
labels:
  - debt
dependencies: []
references:
  - PR #36 (TASK-18)
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio/cli.py` `cmd_research` / `_write_decision_json` leave `source` and `model` as null for the paid CLI path (only `record_rating` from session mode fills them), so `evaluate` cannot split cheap-tier vs heavy-tier hit rates for ratings the desk produced. Thread the configured deep/quick model ids and a `source: "cli"` through from `config`. Reported by the TASK-18 implementer; outside its three ACs.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case test_research_ledger_row_and_sidecar_carry_source_and_model green
<!-- AC:END -->
