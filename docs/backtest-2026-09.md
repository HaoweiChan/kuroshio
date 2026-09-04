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
- **12-1 momentum won the 2021–2026 window, then lost the 2014–2021 one.** Return from
  252 to 21 sessions ago, liquidity gate only, equal-weight top-20 rebalanced monthly:
  +117% through 2025 vs SPY +65%, positive in 2022, all 8 pre-declared cells ahead of SPY.
  Out of sample (2014-06 → 2021-07) the same rule returned +58% vs SPY +156% and vs an
  equal-weight all-members book +139% — 34 points *below* just holding every member
  equally. The sign of its selection effect flips between the two windows; the 9-month
  variant that wins out of sample loses in sample. **No price-only ranking tested here
  beats SPY, or the equal-weight universe, in both windows.** 12-1 is still the better
  of the two US screens (lower turnover, ahead of the leadership screen in the recent
  window, an academic prior) and is now the `us` default; it is not a demonstrated edge.
- **Volatility is a risk control, not an edge.** Sharpe-scaling, low-vol filters, a
  momentum+low-vol composite, inverse-vol weights and a 15% book vol target all move the
  12-1 result toward the other window and none beats SPY in both; the vol target is the
  one that cuts the blowoff-window drawdown to −14%, at a 30-point out-of-sample cost.
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
| Out of sample | Same lab, `--end 2021-07-31 --years 7`: membership from 2013-06-01 (211 snapshots, 760 names, 600 with prices), window 2014-06-20 → 2021-07-30. **111 of the 184 names removed since 2013 have no price history** — worse than the in-sample 48 of 97. |
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

### C. `us` through the allocator

Same harness A, the new profile, `kuroshio simulate --market us --members-file`
(window 2021-07-29 →):

| | strategy | EW top-k of the same ranker | SPY |
|---|---|---|---|
| top-20, monthly: full period | +214.5% | +231.3% | +87.7% |
| top-20, monthly: through 2025 | +110.8% | +116.9% | +64.7% |
| top-20, monthly: max drawdown / turnover | −28.9% / 2.3×/yr (93 swaps, 47 decides) | −32.9% / 7.8× | |
| top-10, weekly: full period | +330.4% | +365.3% | +87.7% |
| top-10, weekly: through 2025 | +148.9% | +173.9% | +64.7% |

`kuroshio backtest --market us --members-file --top 20`: 253 rebalances, mean
top-20 20-day forward +2.19%, excess over SPY +1.10%, beat rate 60%, rank-IC +0.018,
quintiles monotone (Q1 +0.68% → Q5 +1.31%). On this signal the allocator still gives up
6–25 points of return against plain equal weight, but with a third of the turnover and
a smaller drawdown — the rules are no longer the problem; they are a tax whose size
task-1 and task-3 should be measured against.

### D. Out of sample, 2014-06 → 2021-07

Same rankers, same grid, the seven years before the in-sample window. SPY +155.8%.
Equal-weight all live members, rebalanced monthly: +138.8% — the fair benchmark for
an equal-weight top-k book.

| ranker, monthly | 2014–2021 total | vs EW universe | 2021–2025 vs EW universe (in sample) |
|---|---|---|---|
| 12-1 momentum top-20 | +58% | **−34 pts** | **+53 pts** |
| current leadership composite top-20 | +88% | −21 | −19 |
| dip leader by 6m RS, top-10 | +148% | +4 | −13 |
| 9-month (189-21) momentum top-20 | +165% | +10 | −7 (vs SPY) |
| 6-month (126-21) momentum top-20 | +123% | −7 | +18 (vs SPY) |

Every 12-1 cell (weekly/monthly × top-10/20, skip 0/1/2, top-30/50, friction) trails
SPY by 54 to 119 points in this window; rank-IC is −0.016 (48% of months positive,
n=85). The breadth overlay again hurts (+27% vs +58% unhedged). Year by year, 12-1
lost in 2016 (−0% vs SPY +12%), 2018 (−11% vs −4%) and 2021 H1 (+2% vs +18%): the
reversal years, exactly where a momentum book is supposed to be weakest.

Read together with B: the 2021–2026 result was one regime (memory/semiconductor
leadership persisting for years), not a property of the rule. This is also why the
breadth overlay looked like a loser both times — the two windows disagree on
everything except that.

### E. Volatility variants of 12-1 momentum

Seven pre-declared variants, monthly top-20, both windows (`scripts/funnel_lab.py --vol`).
Through-cutoff return; excess vs SPY in brackets.

| variant | 2021–2025 (SPY +65%) | 2014–2021 (SPY +156%) | max dd in / out |
|---|---|---|---|
| 12-1, equal weight (reference) | +117% (+52) | +58% (−98) | −33% / −39% |
| 12-1 ÷ 1-year vol ("Sharpe momentum") | +69% (+4) | +88% (−68) | −30% / −36% |
| 12-1 after dropping the top-vol quintile | +54% (−11) | +98% (−58) | −21% / −39% |
| rank(12-1) + rank(−vol), equal weight | +29% (−35) | +131% (−25) | −22% / −35% |
| 12-1, inverse-vol weights | +115% (+50) | +54% (−102) | −30% / −40% |
| 12-1, book vol target 15% | +74% (+9) | +28% (−128) | **−14%** / −26% |
| min-vol top-20 (reference) | +27% (−37) | +120% (−36) | −19% / −34% |

Every volatility adjustment moves the result *toward* the other window: it costs
return in 2021–2026 and adds it in 2014–2021, which is what you expect from a factor
that is anti-correlated with the momentum blowoff. None crosses the bar. The composite
rank(12-1)+rank(−vol) is the most stable (−35 / −25 vs SPY) and still loses both times;
inverse-vol weighting is a wash; the 15% vol target is the one drawdown tool that works
(−14% in the blowoff window) and it pays for that with 30 points of out-of-sample return.
Volatility is a risk control here, not a source of edge.

## What this means for the design

1. **There is no price-only quant base to build on.** Two windows, five rankers, ~30
   configurations: nothing beats SPY or the equal-weight universe in both. `us` (12-1)
   is the default because it is the less bad of the two screens, not because it is
   an edge. Any stock-selection claim for Kuroshio has to come from data the panel does
   not have — fundamentals and estimate revisions — or from the qualitative layer,
   and both must be measured on this harness before they get weight.
2. **Design sizing and rebalancing on this harness, and only once there is a signal.**
   Every allocator rule tested so far subtracts from the ranking it manages
   (section A; a 6–25 point tax on `us` in section C). Sizing a signal with no edge is
   premature; task-1 and task-3 wait for one, and are then judged by "beats EW top-k of
   the same ranker" in both windows.
3. **Give `turnover.hurdle` a unit.** The IPS must name the cross-section a hurdle is
   measured on (the index, not the book), or the number means nothing.
4. **The fundamentals pipeline and the forward ledger are now the critical path**, not
   optional follow-ups: they are the only routes to a signal this report could not
   find. Snapshot forward P/E and estimates on every run from day one (task-2 data
   half), and log every score and rating for realized-IC (task-4).
5. **Dip buying needs fundamentals.** The price-only version loses in sample and is
   the only ranker near SPY out of sample (dip leader by 6m RS: +4 vs the universe) —
   inconclusive, not evidence.

## Caveats

- **Residual survivorship.** Half the names removed since 2020, and 60% of those removed
  since 2013, have no price history at the provider. Momentum would have held some of the acquired ones (positive) and some of
  the failures (negative); the net sign is unknown. Ticker renames (FB→META, K) are not
  tracked.
- **Two windows, still no 2009-style momentum crash.** 2014–2021 adds 2016, 2018 Q4 and
  the 2020 V — enough to flip the 12-1 result, not enough to bound its tail.
- **Multiple comparisons.** 20 grid cells plus 9 robustness runs per window. 12-1
  momentum was pre-declared as the academic baseline and won every in-sample cell with
  the same yearly shape — which is what a real effect looks like right up until the
  out-of-sample run, where it lost every cell. The lesson is the one the out-of-sample
  run was for.
- **Rebalance timing and prices.** Trades at the close of the signal day; no slippage
  beyond the flat friction; membership after 2026-05-07 is today's roster.

## Reproduce

```bash
python scripts/sp500_members.py members.csv --since 2020-01-01
python scripts/funnel_lab.py members.csv --panel panel.pkl
python scripts/sp500_members.py members-2013.csv --since 2013-06-01
python scripts/funnel_lab.py members-2013.csv --panel panel-oos.pkl --end 2021-07-31 --years 7 --cutoff 2021-07-31
python scripts/funnel_lab.py members.csv --panel panel.pkl --vol
python scripts/funnel_lab.py members-2013.csv --panel panel-oos.pkl --cutoff 2021-07-31 --vol
kuroshio simulate --market us-leadership --ips examples/ips-balanced.md --members-file members.csv --weeks 260 --top 10
kuroshio simulate --market us --ips examples/ips-balanced.md --members-file members.csv --weeks 260 --top 20 --step 21
kuroshio backtest --market us --members-file members.csv --weeks 260 --top 20
```

The lab runs in about 15 seconds from a cached panel; each `simulate` is about a minute
plus an 18-second fetch.
