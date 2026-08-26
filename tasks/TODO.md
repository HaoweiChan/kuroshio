# TODO — pr-loop working set

Two sections, one shared id sequence. `## Queue` is runnable work in priority
order; `## Debt` is findings/overflow logged by pr-loop runs. Merged work moves
to a one-liner in [DONE.md](DONE.md). Format and rules: groundwork pr-loop.

Background and rationale for T1–T10: [docs/PORTFOLIO-PLAN.md](../docs/PORTFOLIO-PLAN.md).

## Queue

### T1 — Accept `Hold` in the verdict ladder [status: todo]
Spec: LLM agents emit `Hold` (agents/engine/agents/schemas.py PortfolioRating) but
`VERDICT_ORDER` in core/ips/schema.py only knows `neutral`, so `verdict_at_least`
silently returns False and a researched `Hold` challenger is rejected while an
unresearched name passes the default floor. Map `hold` → `neutral` (alias, not a
sixth rung).
Acceptance: `verdict_at_least("Hold", "neutral")` is True; a test proves a
`Hold`-rated challenger passes a `neutral` floor and fails an `overweight` floor.

### T2 — Make friction a real gate, not a caption [status: todo]
Spec: `friction.{tw,us}_roundtrip_pct` is printed on SWAP cards but never compared
to the score gap (core/allocator/engine.py). ARCHITECTURE.md already describes it
as a gate. Require `gap >= hurdle + friction_pct` before proposing a swap.
Acceptance: a swap whose gap clears the hurdle but not hurdle+friction is not
proposed; existing allocator tests updated; card text still cites friction.

### T3 — Position records with entry state and thesis [status: todo]
Spec: `Holding` (types.py) carries no entry_price, entry_date, or reason — nothing
downstream can reason about "why do I own this". Add optional fields: entry_price,
entry_date, setup_type (enum: value_dip | pullback_add | trend_add | other),
thesis (free text), invalidation_price. Make holdings.yml parsing tolerant of the
new keys (cli.py `Holding(**item)` currently TypeErrors on unknown fields) while
keeping old files valid.
Acceptance: old holdings.yml still loads; new fields round-trip; a holdings file
with unknown keys fails with a clear message naming the key, not a bare TypeError.

### T4 — Wire the screener into propose [status: todo]
Spec: `kuroshio propose` requires hand-typed `score:` in holdings.yml and
`final_score:` in candidates.yml — the user is the integration layer. When scores
are absent, propose should invoke the market's `score_names(gate=False)` on
incumbents (per the scale-compatibility contract in screening/tw.py and us.py)
and the gated screener for candidates, using the configured provider.
Acceptance: `kuroshio propose` with a score-less holdings.yml produces scored
cards end-to-end against a stub provider; hand-written scores still win if present.

### T5 — Thesis-aware alert rules per setup_type [status: todo]
Depends: T3
Spec: today the only ranking axis is MA distance, so value_dip and pullback_add
positions are structurally the "weakest incumbent" and get proposed for sale.
Dispatch monitoring on setup_type: trend_add alerts on trend break (close < MA50
or ATR trail) and drawdown-from-entry; value_dip and pullback_add alert on
breach of invalidation_price, never on MA distance alone. Cards must cite the
setup_type and entry_price in the reason string.
Acceptance: fixture portfolio with one position per setup_type: the trend_add
alerts on an MA break, the value_dip does not, and the value_dip alerts on an
invalidation breach; every card names its setup_type.

### T6 — Forced decision card at max adverse excursion [status: todo]
Depends: T3
Spec: Freeman-Shor discipline — at a configurable loss-from-entry threshold
(IPS key, default -15%), emit a DECIDE card: kill / add-per-plan / rewrite
thesis. No silent holding of losers. Requires entry_price from T3.
Acceptance: position below threshold yields exactly one DECIDE card citing the
IPS clause; position above threshold yields none; threshold read from IPS.

### T7 — Position sizing engine [status: todo]
Depends: T3
Spec: `caps.position_pct` is parsed, validated, documented — and read by nothing;
TRIM/SWAP cards carry no target weight. Compute a target weight per proposal as
the min of three caps, and name the binding cap on the card: (a) position_pct
base; (b) percent-risk: risk_budget_pct × NAV / (entry − invalidation), when both
prices exist; (c) inverse-vol parity toward a portfolio vol target. Start with
(a)+(b); (c) may land as a follow-up if provider vol data is not ready.
Acceptance: TRIM cards state a numeric target weight; a swap proposal for a
position with entry/invalidation prices shows the percent-risk cap binding when
it is the min; unit tests cover each cap being the binding one.

### T8 — Value and quality factors in the screener [status: todo]
Spec: the screener is momentum-only; `MarketDataProvider.fetch_fundamentals`
exists (providers/base.py) and is never called. Add value (composite percentile
of e.g. earnings yield, FCF yield) and quality (e.g. ROE/ROIC, margin) factor
groups to the US screener via fetch_fundamentals, combined as fixed-weight
percentile composites per screening/score.py conventions. No factor timing.
Missing fundamentals degrade gracefully (weight renormalization already does this).
Acceptance: screen output shows per-factor sub-scores; a name with missing
fundamentals still ranks (momentum-only) without NaN; weights live in the
screener config, not code constants.

### T9 — Tolerance-band rebalancing with a turnover budget [status: todo]
Depends: T7
Spec: replace the binary hard-cap TRIM with Daryanani-style relative bands:
flag when a position drifts outside ±band_rel (default 20%) of its target
weight, propose trading back to the band edge (not to target), ranked by drift
severity, subject to the existing max_swaps_per_week style turnover budget.
Acceptance: position at 12.5% vs 10% target with band 20% yields a card whose
proposed weight is the band edge (12%); position at 11% yields none; band and
budget read from IPS.

### T10 — Close the loop: realized IC and R-multiples [status: todo]
Depends: T3, T4
Spec: log every screener run's scores (per ticker, per date) to a local ledger;
a `kuroshio evaluate` command computes realized IC (score vs forward return,
reusing core/backtest.py's Spearman) and, for closed positions, R-multiples
grouped by setup_type — the system grades both the screener and each thesis
style.
Acceptance: after two logged runs on fixture data, evaluate prints an IC and a
per-setup_type expectancy table; ledger is plain files (no DB).

## Debt

(empty — pr-loop runs append here with `Origin:`)
