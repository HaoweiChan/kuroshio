# Backtest 2026-09 — is there a quant base?

Point-in-time S&P 500, 2021 → 2026-09-03, price-only. Two questions: does the current
screener have a cross-sectional edge, and does the allocator's methodology add to it?
Then: what price-only ranking *does* beat SPY before the 2026 blowoff?

## Summary

- **The current US profile has no demonstrated edge.** On the point-in-time universe its
  walk-forward rank-IC is −0.004 (263 rebalances, quintiles non-monotone); the +0.162
  on the 50-survivor demo page was survivorship and small-sample. Equal-weight top-10 of
  the gated screen matched SPY through 2025-12-31 (+74% vs +77%); every point of its
  full-period excess comes from 2026 YTD (MU, SNDK, INTC, MRNA).
- **The stacked-MA gate is a regime filter, not stock selection.** In 2022 almost nothing
  passed, the book sat in cash, and the EW screen lost 1% while SPY lost 18%. That is the
  one behaviour the data supports, and it has nothing to do with which name is picked.
- **The allocator's rules add variance, not return.** The same top-10 list managed by
  `propose()` (hurdle swaps, hard-cap trims, MAE kills, cash redeploy) returned +36% vs
  +194% for plain equal weight. Across a 12-cell grid (hurdle × MAE × swaps/week) the
  5-year result spans +36% to +197% with no monotone axis; the best cell through 2025 is
  +75% ≈ SPY. `turnover.hurdle` has no defined cross-section: the same 0.15 is three rank
  places in a 20-name pool and 15 percentile points of the index, and that difference
  alone moved the result from +224% to +36%.
- **Plain 12-1 momentum is the quant base.** Return from 252 to 21 sessions ago, liquidity
  gate only, equal-weight top-20 rebalanced monthly: +117% through 2025 vs SPY +65%,
  positive in 2022 (+8% vs −18%), positive every calendar year, +231% full period. It
  wins in all 8 pre-declared cells (weekly/monthly × top-10/20), survives 12-0 / 12-2 skip,
  top-30, and 15× the friction; 6- and 9-month lookbacks are weaker. Now shipped as the
  `us-mom12` profile.
- **Price-only dip funnels lose.** "Pullback inside an intact uptrend" ranked by 12-1
  momentum or 6-month RS trails SPY in 7 of 8 cells. Quality-at-a-discount needs
  fundamentals the panel does not have; that funnel is untested, not refuted.
- **A breadth regime overlay hurts everything** (2022 whipsaw, late 2023 re-entry):
  SPY-when-breadth ≥ 50% returned +45% through 2025 vs +65% for SPY held.

## Setup

| | |
|---|---|
| Universe | S&P 500 point-in-time: `scripts/sp500_members.py` walks today's Wikipedia roster back through the changes table of the last revision that carried it (2026-05-23). 83 snapshots 2020-01-01 → 2026-05-07, 616 distinct names, 503–511 members per date. |
| Prices | yfinance adjusted close + volume, 2020-07-17 → 2026-09-03, 1541 sessions. 568 of 617 tickers resolved; the 49 missing are the acquired/failed removals (ABMD, ATVI, CERN, FRC, …) — **48 of the 97 names removed since 2020 could not be held**. |
| Harness A | `kuroshio simulate` — allocator-managed book (`propose()` every 5 sessions), window 2021-05-18 →, `examples/ips-balanced.md`, top-10 unless stated. |
| Harness B | `scripts/funnel_lab.py` — equal-weight top-k of one ranker, rebalanced every `step` sessions, no `propose()`, window 2021-07-29 → (needs 252 sessions of history). |
| Friction | 0.02% round-trip per swap (the balanced IPS), charged per leg. |
| SPY | +101.5% (A window), +87.7% (B window); through 2025-12-31: +76.8% / +64.7%. |

## Results

### A. Current profile through the allocator

| | strategy | EW top-10 (weekly) | SPY |
|---|---|---|---|
| Full period | +36.0% | +194.1% | +101.5% |
| Through 2025-12-31 | +4.2% | +73.6% | +76.8% |
| 2022 | −21.8% | −0.7% | −18.2% |
| Max drawdown | −32.2% | | |
| Turnover | 17.5×/yr (479 swaps, 6 trims, 39 decides) | | |

Grid over `turnover.hurdle` ∈ {0.15, 0.30, 0.50} × `max_adverse_excursion_pct` ∈ {−15, off}
× `max_swaps_per_week` ∈ {2, 10}: total return +36% … +197%, through-2025 −6% … +75%,
final book 10–34 names. No axis is monotone; MAE on/off has no consistent sign.

### B. Funnel lab (equal-weight top-k, no allocator)

Through 2025-12-31, excess over SPY (+64.7%); full period in brackets.

| ranker | weekly top-10 | weekly top-20 | monthly top-10 | monthly top-20 |
|---|---|---|---|---|
| current gate composite | −5 pts (+183%) | −18 (+122%) | −67 (+97%) | −50 (+62%) |
| **12-1 momentum** | **+109 (+365%)** | **+62 (+247%)** | **+46 (+296%)** | **+52 (+231%)** |
| 12-1 momentum, above MA200 only | +75 (+311%) | +27 (+198%) | +35 (+262%) | +23 (+187%) |
| dip leader, ranked by 12-1 | −11 (+65%) | −30 (+43%) | +7 (+63%) | −37 (+36%) |
| dip leader, ranked by 6m RS | −79 (−4%) | −63 (+10%) | −40 (+28%) | −41 (+27%) |

12-1 momentum, monthly top-20, by year: 2021 (Aug–Dec) +9%, 2022 +8%, 2023 +16%,
2024 +27%, 2025 +25%, 2026 YTD +53%. Max drawdown −33%, turnover 7.8×/yr.

Robustness of the winner (monthly top-20, through-2025 excess over SPY): skip 0 months
+66 pts, skip 2 months +70, 6-month lookback +18, 9-month −7, top-30 +36, top-50 +14,
6-week rebalance +39, friction 0.10% +49, friction 0.30% +41.

Rank-IC vs 20-day forward return, monthly, all liquid members: 12-1 momentum +0.029
(62% of months positive, n=61); current gate composite on its gated pool +0.014 (47%).

### C. `us-mom12` through the allocator

Same harness A, the new profile, `kuroshio simulate --market us-mom12 --members-file`
(window 2021-07-29 →):

| | strategy | EW top-k of the same ranker | SPY |
|---|---|---|---|
| top-20, monthly: full period | +214.5% | +231.3% | +87.7% |
| top-20, monthly: through 2025 | +110.8% | +116.9% | +64.7% |
| top-20, monthly: max drawdown / turnover | −28.9% / 2.3×/yr (93 swaps, 47 decides) | −32.9% / 7.8× | |
| top-10, weekly: full period | +330.4% | +365.3% | +87.7% |
| top-10, weekly: through 2025 | +148.9% | +173.9% | +64.7% |

`kuroshio backtest --market us-mom12 --members-file --top 20`: 253 rebalances, mean
top-20 20-day forward +2.19%, excess over SPY +1.10%, beat rate 60%, rank-IC +0.018,
quintiles monotone (Q1 +0.68% → Q5 +1.31%). On this signal the allocator still gives up
6–25 points of return against plain equal weight, but with a third of the turnover and
a smaller drawdown — the rules are no longer the problem; they are a tax whose size
task-1 and task-3 should be measured against.

## What this means for the design

1. **Build on `us-mom12`, not on the leadership gate.** The gate's regime behaviour can be
   kept as a separate, explicit rule later; as a ranking it is noise.
2. **Design sizing and rebalancing on this harness.** Every allocator rule tested so far
   subtracts from the signal. Task-1 (sizing), task-3 (bands) and any MAE / hurdle change
   should be run through `kuroshio simulate --members-file` before they are accepted, with
   "beats EW top-k of the same ranker through 2025" as the bar.
3. **Give `turnover.hurdle` a unit.** The IPS must name the cross-section a hurdle is
   measured on (the index, not the book), or the number means nothing.
4. **The qualitative layer's job is unchanged**: veto, levels, thesis tracking — and it
   still has to earn its weight through the forward ledger (task-4). Nothing here makes
   that case for it.
5. **Dip buying needs fundamentals.** The price-only version loses; forward P/E and
   estimate revisions are the test that has not been run.

## Caveats

- **Residual survivorship.** Half the names removed since 2020 have no price history at
  the provider. Momentum would have held some of the acquired ones (positive) and some of
  the failures (negative); the net sign is unknown. Ticker renames (FB→META, K) are not
  tracked.
- **One five-year window, no momentum crash.** 2021–2026 contains a bear year but not a
  2009-style reversal; max drawdown of −33% to −38% is what the strategy looks like in a
  good window.
- **Multiple comparisons.** 20 grid cells plus 9 robustness runs. 12-1 momentum was
  pre-declared as the academic baseline and wins every cell with the same yearly shape,
  which is what a real effect looks like — but this is still one sample.
- **Rebalance timing and prices.** Trades at the close of the signal day; no slippage
  beyond the flat friction; membership after 2026-05-07 is today's roster.

## Reproduce

```bash
python scripts/sp500_members.py members.csv --since 2020-01-01
python scripts/funnel_lab.py members.csv --panel panel.pkl
kuroshio simulate --market us --ips examples/ips-balanced.md --members-file members.csv --weeks 260 --top 10
kuroshio simulate --market us-mom12 --ips examples/ips-balanced.md --members-file members.csv --weeks 260 --top 20 --step 21
kuroshio backtest --market us-mom12 --members-file members.csv --weeks 260 --top 20
```

The lab runs in about 15 seconds from a cached panel; each `simulate` is about a minute
plus an 18-second fetch.
