---
id: TASK-2
title: Value and quality factors in the screener
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T8
  - docs/backtest-2026-09.md §1, §4 — fundamentals are the only route to an edge this harness could not find
  - TASK-8 (the data half: the snapshot this task ranks on)
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The screener still ranks on price alone. The **data half of this task has shipped**:
`fetch_fundamentals` is no longer uncalled — `screen`/`research` snapshot it into the
score ledger (TASK-8), and `kuroshio evaluate` already prints realized earnings-yield IC
and revision-breadth IC. What is left is the **ranking half**: those fields reaching
`final_score`.

Add value (composite percentile of e.g. earnings yield, FCF yield) and quality (e.g.
ROE/ROIC, margin) factor groups to the US screener as fixed-weight percentile composites
per screening/score.py conventions. No factor timing. Missing fundamentals degrade
gracefully (weight renormalization already does this). Weights live in the screener
config, not code constants.

Gated on evidence, not on effort. docs/backtest-2026-09.md §1 is explicit that nothing
gets weight before it is measured on this harness, and §4 made the ledger the critical
path precisely so this task would have a number to point at. Do not open this until
`evaluate` has enough logged dates for its earnings-yield / revision-breadth IC to mean
something; then weight the factors by what it says, and give a factor with no measured
IC no weight at all.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 screen output shows per-factor sub-scores; a name with missing fundamentals still ranks (momentum-only) without NaN; weights live in the screener config, not code constants.
- [ ] #2 each factor's weight cites the realized IC that set it (an `evaluate` run or a backtest section); a factor with no measured IC gets zero weight.
<!-- AC:END -->
