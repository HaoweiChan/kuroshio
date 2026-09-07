---
id: TASK-4
title: 'Close the loop: R-multiples per setup_type'
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T10
  - docs/backtest-2026-09.md §4 — the forward ledger is the critical path
  - TASK-6 (the IC half, shipped)
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Half of this shipped as TASK-6.** `core/ledger.py` logs every `screen`/`research` run's
scores and ratings to plain JSONL, and `kuroshio evaluate` reads them back for realized
rank-IC, top-k forward return vs. benchmark, earnings-yield and revision-breadth IC, and
per-rating hit rate. The screener half of "grade both the screener and each thesis style"
is done.

What is left is the **thesis half**: R-multiples grouped by `setup_type`. Nothing in the
repo records a closed position — there is no exit price, no exit date, no closed-trade
row anywhere — so this is two pieces: a way for a position to leave the book with its exit
recorded (the ledger already has the `stop` rows the trail writes, so the shape is
established), and an expectancy table in `evaluate` keyed on `setup_type`, where R is the
realized move over the entry-to-invalidation distance the position was sized on.

This is what tells the owner whether `value_dip` or `trend_add` is the style that actually
pays — the one grading question the shipped half cannot answer.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 after two logged runs on fixture data, evaluate prints an IC; ledger is plain files (no DB).
- [ ] #2 a position can be recorded as closed (exit price + date) without a new store — the existing JSONL ledger carries it.
- [ ] #3 evaluate prints a per-setup_type expectancy table (n, mean R, win rate) over closed positions, and says so rather than printing an empty table when none are recorded.
<!-- AC:END -->
