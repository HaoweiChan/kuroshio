---
id: TASK-5
title: Portfolio simulator over walk-forward
status: In Progress
assignee: []
created_date: '2026-09-03'
labels: []
dependencies: []
references:
  - core/backtest.py
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`core/backtest.py:walkforward` measures whether `final_score` ranks forward returns; it never runs the allocator, so the sizing / swap / trim / max-adverse-excursion rules that make up the methodology have no backtest at all. Add `core/simulate.py:simulate(...)`: a pure walk-forward loop that, on each rebalance date, builds the portfolio from the gated screen, scores incumbents and challengers in one ungated `score_names` cross-section, calls `propose()` with `monitor_inputs` of the panel sliced to that date, applies the cards mechanically (SWAP, TRIM to the hard cap, DECIDE as kill; ALERT ignored), charges `ips.friction` per leg, and lets weights drift with prices between rebalances. Report NAV path, max drawdown, annualized turnover, trade counts, and the same numbers for an equal-weight top-k baseline and the benchmark. `kuroshio simulate` wires it to the same fetch as `backtest` and prints the survivorship caveat. `screen_fn` stays a parameter so a second funnel plugs in later. Pure quant only: no verdicts, no rating hook.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 on a synthetic panel, simulate returns a NAV path that starts at 1.0 and is finite; a ticker that drops through `caps.max_adverse_excursion_pct` is sold via a DECIDE trade and absent afterwards; positions never exceed `caps.position_hard_pct` right after a rebalance; non-zero friction lowers final NAV against zero friction with the same trades; all without network.
<!-- AC:END -->
