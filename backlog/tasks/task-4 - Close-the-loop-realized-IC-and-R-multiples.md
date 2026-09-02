---
id: TASK-4
title: 'Close the loop: realized IC and R-multiples'
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T10
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
log every screener run's scores (per ticker, per date) to a local ledger; a `kuroshio evaluate` command computes realized IC (score vs forward return, reusing core/backtest.py's Spearman) and, for closed positions, R-multiples grouped by setup_type — the system grades both the screener and each thesis style.

Depends (TODO.md ids): T3, T4

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 after two logged runs on fixture data, evaluate prints an IC and a per-setup_type expectancy table; ledger is plain files (no DB).
<!-- AC:END -->
