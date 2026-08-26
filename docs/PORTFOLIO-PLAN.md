# Portfolio Management — Diagnosis and Plan

An audit of Kuroshio's portfolio-management logic (2026-08-26), the active
portfolio management literature it should borrow from, and a phased plan.
The plan is executable: each phase maps to task ids in
[tasks/TODO.md](../tasks/TODO.md), run via groundwork's `/pr-loop`.

## The complaints

1. Alerts are incoherent — positions entered on different theses (low-P/E
   value dips, pullback adds on prior winners, trend-following adds) all get
   judged by moving averages, never by their entry price or entry reason.
2. Weight/ratio control has no explicit logic.
3. The screener is weak.

The audit found all three are literal properties of the code, not perception.

## Diagnosis

**Positions have no memory.** `Holding` (`kuroshio/types.py`) is
`{ticker, weight, theme, leverage, score, verdict}` — no entry price, entry
date, cost basis, or entry reason, anywhere. The LLM pipeline *suggests*
`entry_price`/`stop_loss` for new trades (`agents/engine/agents/schemas.py`)
but nothing persists them against a position and nothing in `core/` reads them
back. `cli.py` parses holdings with a strict `Holding(**item)` splat, so the
fields cannot even be added to `holdings.yml` today. Every alert keyed to
entry state is structurally impossible. This is the root cause.

**There is no price-alert system — and MA distance is the only ranking
axis.** The only "alerts" are the five allocator card types
(`core/allocator/engine.py`): theme cap breach, no-scores, suppressed swaps,
hard-cap TRIM, score-gap SWAP. The MA problem is upstream: the TW score is
built from `close/ma20`, `close/ma60`, and volume (`core/screening/tw.py`);
the US score from stacked 20/50/200 MAs and distance to the 60-day high
(`core/screening/us.py`). A value-dip or pullback-add position scores badly
*by construction*, becomes `min(pool, key=score)` — the weakest incumbent —
and is the first name the engine proposes to sell. The engine actively
targets exactly the positions bought on a dip thesis.

**Sizing logic is absent, literally.** `caps.position_pct` — the IPS
"standard position size" — is parsed, validated, and written about in all
three IPS presets, and read by no code. `propose()` never emits a target
weight: TRIM says "trim it back" with no number, SWAP is ticker-for-ticker.
There is no volatility, correlation, Kelly, ATR, or risk-based sizing
anywhere in `core/`. The LLM-side sizing is a flat dict keyed on verdict
(`agents/engine/portfolio/sizing_us.py`).

**The screener is single-factor.** Pure price/volume momentum; zero value,
quality, or fundamentals. `MarketDataProvider.fetch_fundamentals`
(`providers/base.py`) exists and is never called. And the screener is not
wired into `propose` — `score:` and `final_score:` are hand-typed YAML; the
user is the integration layer.

**Two adjacent bugs.** (a) Agents emit `Hold`, but `VERDICT_ORDER`
(`core/ips/schema.py`) only knows `neutral`; the lookup's `ValueError` is
swallowed as `False`, so a researched `Hold` challenger fails a `neutral`
floor that an unresearched name passes by default. (b) `friction_pct` is
printed on SWAP cards but never compared to the gap — ARCHITECTURE.md
describes a gate; the code ships a caption.

## What the literature prescribes

- **Grinold & Kahn, *Active Portfolio Management*** — IR = TC × IC × √breadth;
  refine signals into cross-sectional z-scores, then α = IC × residual vol ×
  score, and active weight ∝ α / (λσ²). Practically: keep scores comparable,
  log forecasts so realized IC can be measured later — the screener must
  grade itself.
- **Position sizing** — Thorp/Kelly (always fractional, ¼–½, because edge
  estimates are noisy); van Tharp percent-risk (risk 0.5–2% of equity per
  position, size = risk budget ÷ distance to invalidation, outcomes tracked
  as R-multiples); volatility parity (w ∝ 1/σ). Consensus: several simple
  caps, take the min, and say which one bound.
- **Thesis-driven process** — Lynch (*One Up on Wall Street*): every holding
  belongs to a category, and each category has its own monitoring variables
  and sell rule; a cheap-looking cyclical at peak earnings is a trap.
  Rappaport & Mauboussin (*Expectations Investing*): the thesis is the gap
  between price-implied expectations and your view — checkable, not vibes.
  Klein: write the pre-mortem at entry. The IPS presets already promise
  "thesis break" handling in prose; the code has no thesis object.
- **Exit discipline** — Freeman-Shor (*The Art of Execution*): only ~49% of
  top managers' best ideas made money, yet nearly all managers profited —
  returns come from the response to being wrong. At a material loss the only
  valid moves are kill or materially add, per a plan chosen at entry; never
  silent holding. Shefrin/Statman/Odean: the disposition effect is the
  default failure mode to engineer against.
- **Rebalancing** — Daryanani: relative tolerance bands (±20% of target
  weight), look often, trade rarely, trade back to the band edge (not to
  target), under a turnover budget. Beat calendar rebalancing by ~50 bp/yr
  in his study.
- **Screeners** — O'Shaughnessy (*What Works on Wall Street*): composites of
  4–6 ratios beat any single ratio, in percentile-rank space. Asness et al.:
  hold factor weights static — factor timing is "deceptively difficult".
  Greenblatt: two ranks summed already works. Momentum + value + quality,
  fixed weights, cross-sectional percentiles — which is exactly the shape
  `core/screening/score.py` already implements for momentum alone.

## The plan

Phases in dependency order; ids are pr-loop tasks in
[tasks/TODO.md](../tasks/TODO.md).

**Phase 0 — stop the bleeding (T1, T2, T4).** Fix the `Hold` verdict hole,
make friction a real gate (`gap ≥ hurdle + friction`), and wire the screener
into `propose` so scores stop being hand-typed. No new concepts, three small
PRs, immediately raises the quality of every card.

**Phase 1 — positions get memory (T3).** Extend `Holding` with
`entry_price`, `entry_date`, `setup_type` (value_dip | pullback_add |
trend_add | …), `thesis`, `invalidation_price`; tolerant YAML parsing. The
load-bearing change — every later phase depends on it.

**Phase 2 — thesis-aware monitoring (T5, T6).** Dispatch alert rules on
`setup_type`: trend adds alert on trend break and drawdown-from-entry; value
dips alert on invalidation breach, never on MA distance. At −15% from entry,
emit a forced DECIDE card — kill / add per plan / rewrite thesis (Freeman-
Shor). Cards cite setup_type and entry price.

**Phase 3 — sizing gets logic (T7, T9).** Target weight = min(position_pct
base, percent-risk cap from entry−invalidation distance, inverse-vol parity),
with the binding cap named on the card. Then replace the binary hard-cap trim
with Daryanani bands under the existing turnover budget.

**Phase 4 — a screener that grades itself (T8, T10).** Add value and quality
composites via the already-defined `fetch_fundamentals`, fixed weights, no
factor timing. Log every run's scores; `kuroshio evaluate` reports realized
IC and per-setup_type R-multiple expectancy — telling you which thesis styles
you should stop trading.

## What this deliberately does not include

Order execution and multi-tenancy stay non-goals (ROADMAP). No optimizer, no
covariance estimation, no Kelly beyond the fractional caps above — Grinold's
full mean-variance machinery is a later conversation, after realized IC data
exists to feed it.
