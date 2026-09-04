---
id: TASK-8
title: Estimates, revisions, insider and earnings dates in the snapshot and the fundamentals analyst
status: Done
assignee: []
created_date: '2026-09-04'
labels: []
dependencies:
  - TASK-6
references:
  - docs/backtest-2026-09.md §What this means, items 4 and 5
  - TASK-2 (data half)
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The forward record (TASK-6) snapshots forward P/E only. The one fundamentals signal the report singles out — estimate *revisions*, not levels — and the three data gaps the engine's fundamentals analyst has (revisions, earnings calendar, insider transactions) are all available keyless in yfinance 1.5.1: `Ticker.eps_revisions` (up/down counts, 7d/30d, per period), `earnings_estimate`, `recommendations_summary`, `insider_transactions`, `calendar["Earnings Date"]`, `earnings_dates` (with surprise %). Verified 2026-09-04 on AMD: six extra calls, about 3 s per name in total.

Two halves. (a) Kuroshio: `providers/yf.py:fetch_fundamentals` adds `eps_rev_up_30d`, `eps_rev_down_30d`, `eps_est_growth_fy`, `n_analysts`, `rec_buy`, `rec_hold`, `rec_sell`, `next_earnings_date`, `last_surprise_pct`, `insider_net_shares_90d` (purchases minus sales); every field `None` when the table is missing; `core/ledger.realized` adds `rev_ic`, the rank-IC of revision breadth `(up − down) / (up + down)` vs forward return. (b) Engine (vendored, minimal, additive): a `get_analyst_estimates` dataflow + tool and the existing `get_insider_transactions` wired into the fundamentals analyst's tool list and prompt, so the LLM sees revisions and insider activity instead of only the three statements.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth (engine half: dataflow formatting tested against a stubbed `yf.Ticker`; no LLM run)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 with a stubbed provider, a `screen` run writes snapshot rows carrying the new fields; a ticker whose tables are missing gets `None` in each without failing; `evaluate` prints `rev_ic` when ≥ 3 rows carry revisions; the fundamentals analyst's tool list contains the estimates and insider tools and its dataflow renders a stubbed `eps_revisions` / `insider_transactions` frame into the text the tool returns.
<!-- AC:END -->
