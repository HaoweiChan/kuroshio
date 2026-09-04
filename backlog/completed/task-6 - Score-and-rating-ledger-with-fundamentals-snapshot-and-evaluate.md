---
id: TASK-6
title: Score and rating ledger, fundamentals snapshot, `kuroshio evaluate`
status: Done
assignee: []
created_date: '2026-09-04'
labels: []
dependencies: []
references:
  - TASK-4 (realized IC half)
  - TASK-2 (data half only — no new screener factors)
  - docs/backtest-2026-09.md §What this means, items 1 and 4
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/backtest-2026-09.md found no price-only ranking that beats SPY in both windows, so the only routes to a signal are data the panel does not carry (fundamentals, estimates) and the qualitative layer — and both need a forward record from day one. Add a plain-file ledger under `$KUROSHIO_LEDGER_DIR` (default `~/.kuroshio/ledger/`): every `kuroshio screen` run appends one JSONL row per candidate (run date, market, profile, ticker, rank, final_score, scores, factors, close) plus a fundamentals snapshot (forward P/E, forward EPS, trailing EPS, market cap, sector) for the top-N screened names, fetched through a new `providers/yf.py:fetch_fundamentals`; every `kuroshio research` run appends the rating and the risk-control levels. `kuroshio evaluate --market us --horizon 20` reads the ledger, fetches forward prices once, and prints realized rank-IC per run date, top-k forward return vs benchmark, realized IC of forward earnings yield, and per-rating hit rate and mean forward return. Per-setup_type R-multiples (the other half of TASK-4) need a closed-trades record that does not exist yet and stay out of scope.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 with a stubbed provider, two `screen` runs on different dates append rows a third run can read back unchanged; `evaluate` on those rows plus stubbed forward prices prints a rank-IC per date and a top-k vs benchmark line; a `research` run appends a rating row and `evaluate` prints a per-rating table; fundamentals missing for a ticker leave that row's snapshot fields null without failing the run; all without network.
<!-- AC:END -->
