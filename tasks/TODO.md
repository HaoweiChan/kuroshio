# TODO — pr-loop working set

Two sections, one shared id sequence. `## Queue` is runnable work in priority
order; `## Debt` is findings/overflow logged by pr-loop runs. Merged work moves
to a one-liner in [DONE.md](DONE.md). Format and rules: groundwork pr-loop.

Background and rationale for T1–T10: [docs/PORTFOLIO-PLAN.md](../docs/PORTFOLIO-PLAN.md).

## Queue

### T2 — Make friction a real gate, not a caption [status: pr]
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

### T11 — Decide whether `hold` is a legal IPS `verdict_floor` spelling [status: todo]
Origin: PR #3 R1, R2
Spec: T1 made `_rank` alias `hold` → `neutral` on *both* arguments of
`verdict_at_least`, so `verdict_at_least("buy", "hold")` is True — but
`validate()` (core/ips/parser.py:124) still rejects `turnover.verdict_floor: hold`
against `VERDICT_ORDER`, and `cmd_propose` exits 2 on any validate problem. The
same word is legal as an agent verdict and illegal as a user-authored floor. Pick
one: accept `hold` in validation (share the alias helper, list it in the error
message), or narrow `_rank` to the verdict argument only and drop the
`verdict_at_least("buy", "Hold")` assertion in tests/test_ips.py:112. Whichever
way it goes, docs/ARCHITECTURE.md:128 and the `examples/ips-*.md` comments still
enumerate only the five canonical names and must say what `hold` does (R2).
Acceptance: `kuroshio ips-validate` and `verdict_at_least` agree on whether
`hold` is a legal floor, proven by a test; the ARCHITECTURE.md verdict-vocabulary
line matches the decision.
Out of scope: adding a sixth rung — `hold` stays an alias either way.

### T12 — Unrecognized challenger verdicts fail silently [status: todo]
Origin: PR #3 R3
Spec: `_rank` matches exactly after `.lower()` with no `.strip()`, so
`verdict_at_least(" hold ", "neutral")` is False while `"hold"` is True — a
quoted trailing space in candidates.yml (plausible from a pasted research report)
drops the challenger. The allocator compounds it: core/allocator/engine.py:102
`continue`s with no ALERT when the floor is not cleared, so an unparseable verdict
produces zero output rather than a diagnostic. This is the same silent-False class
of bug T1 was written to close, one layer out.
Acceptance: a challenger whose verdict string is unrecognized (not merely
low-rated) surfaces a visible ALERT card rather than vanishing; whitespace-padded
verdicts rank correctly, covered by a test case.

### T14 — Unknown market strings silently take the cheaper US friction [status: todo]
Origin: PR #4 R3
Spec: core/allocator/engine.py:94 picks friction with
`"tw_roundtrip_pct" if market.lower() == "tw" else "us_roundtrip_pct"`. Since T2
that choice is a real gate, not a caption, so `' tw'`, `'twse'`, `'jp'`, `'hk'`
and `''` all silently gate at the 0.02% US number and the card cites
`friction.us_roundtrip_pct` for a non-US trade. `propose()` is a documented public
entry point (docs/ARCHITECTURE.md:144) and docs/adding-a-market.md walks
contributors through adding a `jp` market; the CLI's `choices=["us","tw"]`
(cli.py:373) is the only thing currently containing it.
Acceptance: an unrecognized market normalizes or raises explicitly rather than
defaulting to the cheapest friction, covered by a test using a market string that
is neither 'us' nor 'tw'.

### T15 — Gap exactly equal to the friction threshold is rejected [status: todo]
Origin: PR #4 R4
Spec: the gate is `if gap < hurdle` where `hurdle = ips.turnover.hurdle +
friction_pct / 100`, so a gap exactly equal to the threshold should be proposed
per the spec's `>=`. Float representation defeats it: with hurdle 0.15 and TW
friction 0.585 the threshold is 0.15585, while a challenger at 0.55585 against an
incumbent at 0.40 gives a gap of 0.15584999999999993 and is rejected.
Acceptance: the boundary is decided deliberately (an epsilon, or rounding to score
precision) and pinned by a test asserting what happens when the gap equals
hurdle + friction/100 exactly.

### T16 — Refresh the demo screenshot after the card-text change [status: todo]
Origin: PR #4 R2
Spec: PR #4 regenerated the README sample card and the five `demo-data` reason
strings in docs/index.html from a live `propose()` run, but
docs/screenshot-proposals.png still renders the pre-T2 wording ("Estimated
round-trip friction: 0.020%."). It was left stale deliberately — it is the only
member of that artifact set that cannot be regenerated from code. The cards
themselves are unchanged; only the reason text drifted.
Acceptance: docs/screenshot-proposals.png shows the current card text, and the
README alt text and surrounding prose still describe what the image shows.

### T17 — Nothing pins README/docs samples to generated output [status: todo]
Origin: PR #4 R2
Spec: the drift PR #4 fixed can recur the next time card text changes — no test
compares the README sample card or the docs/index.html `demo-data` reason strings
against `to_markdown()` / `propose()`. The blocker is that the demo inputs
currently live only inside the published HTML blob, so there is no fixture to
drive a regeneration from.
Acceptance: the demo inputs live somewhere a test can read, and a test fails when
the README sample or the docs demo reasons diverge from generated output.

### T18 — Friction validation message names a rule the value satisfies [status: todo]
Origin: PR #4 R7
Spec: core/ips/parser.py:131-132 uses one message for three distinct rejections
(bool, non-numeric, out-of-range), so a wrong-*type* value is reported with a rule
its own printed value meets: `friction.tw_roundtrip_pct ('1e-3') must be a percent
in [0, 100)` — and 0.001 is. The `1e-3` case is the sharp one, since PyYAML 1.1
resolves the no-dot exponent form to a string, so a user writing a perfectly
reasonable number gets an error message that looks wrong. The value is correctly
rejected; only the explanation misleads.
Acceptance: the type failure and the range failure produce distinguishable
messages, asserted by test_validate_catches_bad_friction for `"0.585"` vs `-10.0`.
