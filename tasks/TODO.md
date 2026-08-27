# TODO — pr-loop working set

Two sections, one shared id sequence. `## Queue` is runnable work in priority
order; `## Debt` is findings/overflow logged by pr-loop runs. Merged work moves
to a one-liner in [DONE.md](DONE.md). Format and rules: groundwork pr-loop.

Every `## Debt` block carries a mandatory `Priority: P1|P2|P3` line; `## Queue`
blocks only carry one when the content justifies deviating from the default
(P2, no line needed). Check the board with:
`python3 ~/.claude/plugins/marketplaces/groundwork/plugin/skills/pr-loop/scripts/ready.py`
(run from the repo root).

Background and rationale for T1–T10: [docs/PORTFOLIO-PLAN.md](../docs/PORTFOLIO-PLAN.md).

## Queue

### T6 — Forced decision card at max adverse excursion [status: in-progress]
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
Priority: P2
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
Priority: P1
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
Priority: P1
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
Priority: P1
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
Priority: P3
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
Priority: P2
Origin: PR #4 R2
Spec: the drift PR #4 fixed can recur the next time card text changes — no test
compares the README sample card or the docs/index.html `demo-data` reason strings
against `to_markdown()` / `propose()`. The blocker is that the demo inputs
currently live only inside the published HTML blob, so there is no fixture to
drive a regeneration from.
Acceptance: the demo inputs live somewhere a test can read, and a test fails when
the README sample or the docs demo reasons diverge from generated output.

### T18 — Friction validation message names a rule the value satisfies [status: todo]
Priority: P2
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

### T19 — candidates.yml gets none of the holdings.yml input hygiene [status: todo]
Priority: P2
Origin: T3
Spec: T3 gave `_holdings_from_yaml` (cli.py) unknown-key detection and a clear
`error:`/exit-2 path in `cmd_propose`. PR #6 R4 gave `_candidates_from_yaml` the
same unknown-key check and routed it through the same exit-2 path; what is left is
the *missing*-key half — bare `item["ticker"]` still raises a context-free
`KeyError` traceback out of the CLI. `_load_yaml` also assumes a top-level list: a
file written as a YAML mapping iterates as strings and dies on `item.get`.
Acceptance: a candidates.yml with a missing/misspelled key exits 2 with a message
naming the file and the key; a non-list top-level document is rejected with a
clear message — this covers `_holdings_from_yaml` too, whose `item.get` is the
line that raises `AttributeError` on a non-mapping entry (`- AAPL`); covered by
tests alongside the T3 holdings cases.

### T20 — Missing required holdings key still escapes as a bare TypeError [status: todo]
Priority: P2
Origin: PR #5 R1
Spec: T3 fixed the *unknown*-key TypeError out of `Holding(**item)` (cli.py:58) but
not the *missing*-key one, and cli.py:249-251 catches only `ValueError`. Input
`- {ticker: AAPL}` — a hand-edit that forgot `weight:`, an extremely realistic
holdings.yml typo — produces `TypeError: Holding.__init__() missing 1 required
positional argument: 'weight'` as a full traceback, exit code 1, not the exit-2
`error:` path the same function now provides for `entrey_price`. Out of T3's scope
(its acceptance names unknown keys only), but it is the same line of code.
Acceptance: a holdings item missing `ticker` or `weight` exits 2 with a message
naming the file, the offending entry, and the missing key; covered by a test
alongside test_propose_exits_2_on_unknown_holdings_key.

### T21 — entry_date is coerced but never validated, yet documented as ISO [status: todo]
Priority: P1
Origin: PR #5 R3
Spec: cli.py:55-57 coerces `entry_date` with `str()` and never validates it, while
types.py:49 (`entry_date: str | None = None  # ISO date`) and
docs/ARCHITECTURE.md:68 call it an ISO date. `entry_date: 2025-01-15 10:30:00`
stores `'2025-01-15 10:30:00'` (not an ISO date, and not ISO-8601 datetime either —
no `T`); `entry_date: not-a-date` stores `'not-a-date'`. T5/T6 (drawdown-from-entry,
MAE cards) are specified to consume this field.
Acceptance: either the comment/doc drop the ISO claim, or the loader rejects a value
`datetime.date.fromisoformat` cannot parse with a message naming the ticker and the
value; one test case.

### T22 — Quoted entry_price/invalidation_price stay strings in float fields [status: todo]
Priority: P1
Origin: PR #5 R4
Spec: cli.py:55-57 coerces dates but not the two numeric entry fields. Input
`- {ticker: A, weight: 0.1, entry_price: "180.5", invalidation_price: "150"}` yields
`Holding(entry_price='180.5', invalidation_price='150')` — quoting prices is a common
YAML habit, and T7 (percent-risk cap from the entry−invalidation distance) will do
arithmetic on these.
Acceptance: numeric-string `entry_price`/`invalidation_price` either coerce to float
or raise a message naming the ticker and the key; one test case.

### T23 — Null ticker prints `None` instead of the `?` fallback [status: todo]
Priority: P3
Origin: PR #5 R5
Spec: cli.py:46 `item.get('ticker', '?')` returns None (not `'?'`) when the key is
present but null, so `- {ticker: null, weight: 0.1, bogus: 1}` produces
`holdings.yml: None: unknown key 'bogus'`.
Acceptance: the message reads `?` (or `<no ticker>`) when the ticker is absent or null.

### T24 — Provider fetch + ImportError hint is now copy-pasted three times [status: todo]
Priority: P2
Origin: T4
Spec: `cmd_screen` (cli.py:151-160), `cmd_backtest` and now `cmd_propose` each carry
the same `get_provider(name)` / `fetch_panel(...)` / `except ImportError -> print
'the X provider is not installed' -> return 2` block. T4 followed the existing pattern
rather than widen its diff; the third copy is the one that argues for extracting it.
Acceptance: one helper (e.g. `_fetch_panel(profile, provider_name, tickers, ...)`)
returning the panel or signalling the exit-2 path, used by all three commands, with
the existing provider-missing tests still passing unchanged.

### T25 — propose drops the US `sector` factor because it has no --sector-map [status: todo]
Priority: P1
Origin: T4
Spec: T4 calls `profile.screen(panel)` / `profile.score_names(panel, tickers=...)` with
no `sector_map`, because `propose` has no `--sector-map` flag (`screen`/`backtest` both
do). For `--market us` that silently drops the `sector` factor (0.20 of WEIGHTS) and
renormalizes, so an auto-filled score is not the same number `kuroshio screen
--sector-map ...` would print for the same name on the same day. Same for `--asof`:
propose always scores the latest session.
Acceptance: `propose` accepts `--sector-map` (and, if wanted, `--asof`) and threads it
into both screening calls, matching `cmd_screen`'s `screen_kwargs` handling; one test
proving the sector factor appears in an auto-filled US score.

### T27 — --provider and the us benchmark append have no test that can go red [status: todo]
Priority: P2
Origin: PR #6 R7
Spec: cli.py:449 adds `--provider` to propose and cli.py:288 resolves it; cli.py:293-294
appends `profile.benchmark` for `us`. Every new T4 test uses `--market tw` with
`_use_stub` = `monkeypatch.setattr("kuroshio.providers.get_provider", lambda name: stub)`,
which discards `name` — deleting `args.provider or` from cli.py:288 still leaves the suite
at 121 passed. `profile.benchmark` is None for tw, so cli.py:293-294 never executes in any
test, while docs/ARCHITECTURE.md:202 advertises `[--provider ...]` on propose.
Acceptance: one test asserting `get_provider` is called with the value of `--provider`
(stub captures `name`), and one `--market us` test asserting `SPY` is in the fetched
ticker list.

### T28 — Candidate.final_score is annotated float but now holds None [status: todo]
Priority: P2
Origin: PR #6 R8
Spec: types.py:29 declares `final_score: float`; cli.py:75 now stores
`item.get("final_score")`, i.e. None, and `propose()` in core/allocator/engine.py sorts
challengers by `final_score`, which would raise TypeError if a None ever reached it. Not
reachable through `cmd_propose` today (the `any(... is None)` guard routes to
`_score_missing`, which filters), but `_candidates_from_yaml` is called directly in tests
and is now a documented-optional-field parser with a lying type.
Acceptance: `final_score: float | None` on the dataclass, or `_candidates_from_yaml`
returns only scored candidates.

### T29 — Unknown --provider value is a traceback, not exit 2 [status: todo]
Priority: P2
Origin: PR #6 R9
Spec: `get_provider(provider_name)` is called inside `try: ... except ImportError` in all
three commands (cmd_screen, cmd_backtest, and now cmd_propose at cli.py:296), but
providers/__init__.py:23 raises `ValueError(f"Unknown provider {name!r}...")` — so
`--provider bogus` prints a traceback instead of the exit-2 install hint next to it.
Pre-existing shape, newly reproduced on the propose surface.
Acceptance: `except (ImportError, ValueError)` (or `choices=sorted(_REGISTRY)`) so an
unknown provider exits 2 with the message on stderr, in all three commands.

### T30 — auto-filled scores are percentiles within the user's own files [status: todo]
Priority: P2
Origin: PR #6 R2
Spec: PR #6 put incumbents and challengers on one cross-section, guarded by a minimum
pool size and a disclosure on the card. The guard was re-derived in round 3 (R13): it
keys off the composite's *step* — `profile.min_rank_weight / (n - 1)`, read from each
profile's factor weights — and refuses when that step is >= `turnover.hurdle +
friction/100` (n <= 3 for both markets under the balanced IPS). That is a conservative
heuristic, not an exact minimum step — it over-refuses both when the live composite is
finer than the degraded one (R17) and when the surviving weights are unequal (R19). Above that size the number is still
rank-within-your-portfolio, not strength within a market, and it moves when you add a
ticker to the file; the card discloses that rather than fixing it. The real fix is a
cross-section that is a universe: score against a `--universe` ticker file (or a cached
`kuroshio screen` run's scores) and read the incumbent's and challenger's percentiles
out of that, or give the screener an absolute score.
Acceptance: an auto-filled score for a name is unchanged by adding an unrelated
ticker to holdings.yml, and a 2-name portfolio gets a real universe distance instead
of a refusal; the pool-size guard and the rank-distance disclosure can then go.

### T35 — tw.MIN_RANK_WEIGHT's comment states a market-specific law as a general one [status: todo]
Priority: P3
Origin: PR #6 R19
Spec: `kuroshio/core/screening/tw.py:35` says two names in a pool of n "cannot differ by
less than MIN_RANK_WEIGHT / (n - 1) without tying". That is true for TW, whose degraded
weights are equal (1/3, 1/3, 1/3), and false in general — US degraded is 0.625/0.375 and
reaches smaller gaps (R19). Left as-is because it is correct where it is written, but it
is the sentence someone will copy when adding a market, which is exactly how R19 got in.
Acceptance: the comment scopes the claim to TW's equal degraded weights, or drops the
arithmetic and points at `cli.py:_score_missing` like the US one now does.

### T31 — Drop notice misattributes a provider no-data miss as a gate failure [status: todo]
Priority: P1
Origin: PR #6 R12
Spec: cli.py:295 picks the reason with
`why = "did not pass the Stage-1 gate" if ranked else "could not be auto-scored"` —
keyed off whether the *pool* was ranked, not off why *this* name is missing. A
candidate the provider returned no data for (`- {ticker: "9999", verdict: buy}`,
typo or delisted) is reported as `... did not pass the Stage-1 gate: 9999`. Mirror
case: a holding `9999` gets `h.score = ranked.get(...) -> None` at cli.py:283 and is
excluded from ranking with no notice at all, against the same block's stated
"reported rather than dropped in silence" principle.
Acceptance: the reason is split per name (`not in ranked` -> "no price data returned
by the provider", `not in eligible` -> "did not pass the Stage-1 gate"), unscorable
holdings are reported on stderr too, and a test asserts the no-data wording for a
ticker the stub panel does not contain.

### T32 — details["auto_scored"] is written but nothing reads it [status: todo]
Priority: P2
Origin: PR #6 R15
Spec: core/allocator/engine.py:150 records `"auto_scored": auto` on the card, but
`details` is referenced nowhere in `to_markdown` (types.py:69) or in
integrations/discord.py, and no test asserts it — mutating the line to
`"auto_scored": []` leaves the suite at 128 passed. It also drops the pool size the
prose disclosure carries, so it is not even a machine-readable copy of the sentence.
Acceptance: either the field is dropped (nothing reads it) or one allocator test
asserts it, e.g. `cards[0].details["auto_scored"] == ["1102", "1101"]`, so the
mutation goes red.

### T33 — Disclosed pool size is unpinned when the provider returns fewer names [status: todo]
Priority: P2
Origin: PR #6 R16
Spec: cli.py:275,284 record `len(ranked)` and engine.py:129 prints
`auto_scored[auto[0]]`. Mutating those cli lines to `len(names)` leaves 128 passed,
because every stub panel in tests/test_cli.py contains every requested ticker; the two
numbers diverge only when a provider returns no data for a listed ticker (the T31 case),
where the card then overstates how many names it ranked against. The card also reports
only the first auto-filled ticker's pool size.
Acceptance: one case with a stub panel missing a listed ticker asserts the disclosure
reports the number actually ranked, not the number listed.

### T34 — The US `need` value is pinned by a bucket, not a number [status: todo]
Priority: P2
Origin: PR #6 R19 (reviewer note)
Spec: `test_propose_guards_the_us_pool_too` pins that a 3-name US pool refuses and a
4-name pool scores, which constrains `us.MIN_RANK_WEIGHT` only to the interval
[0.3004, 0.4506) — any value in that range is a silent no-op, so a wrong derivation
inside the bucket ships green. The TW side has the same shape. No test asserts the
printed `need` itself.
Acceptance: one case asserts the `need` value the notice prints for each market, so a
change to `MIN_RANK_WEIGHT` that stays inside the bucket still goes red.

### T36 — Two step-grid sentences left standing in TW-only scope [status: todo]
Priority: P3
Depends: T35
Origin: PR #6 R20 (reviewer note)
Spec: a repo-wide grep after round 6 leaves exactly two step-grid claims: tw.py:33-38
(already T35) and the name plus docstring of
`tests/test_cli.py::test_propose_refuses_when_the_hurdle_cannot_reject_anything`, which
still say "clears the hurdle by construction and the gate cannot reject anything". That
test is TW-only (`--market tw`, degraded 1/3 grid), so the claim is true in its scope,
but it is the same sentence T35 is about and reads as a general law to the next reader.
Acceptance: folded into T35's fix — both sites either scope the claim to equal surviving
weights or stop asserting it.

### T37 — min_rank_weight is documented as the largest share, computed as the smallest [status: todo]
Priority: P1
Origin: PR #6 R20
Spec: six sites define `min_rank_weight` as "the largest share of `final_score` a single
pctrank can control" while the code takes the smallest surviving weight: us.py:33 says
"Largest share ... the composite at its coarsest" and us.py:38 computes
`min(WEIGHTS["momentum"], WEIGHTS["volume"]) / (sum)` = 0.37523, the smaller of
(0.62477, 0.37523). Also cli.py:268, the cli.py:296 notice ("this market's single
coarsest factor weight"), docs/ARCHITECTURE.md:212-213, docs/adding-a-market.md:81 and
core/screening/__init__.py:26. TW is unaffected — its degraded weights are equal, so
largest == smallest. The consequence with teeth: adding-a-market.md instructs a new
market's author to compute the max, which for a 0.625/0.375-shaped profile yields
`need` = 6 where us.py's own rule yields 4. "Conservative, never permissive" is only
derivable from the minimum per-pctrank weight, not from the definition given.
Merged as named debt at the human's direction (option B at the round-6 circuit breaker);
no behaviour is wrong, only the definition.
Acceptance: the six sites describe `min_rank_weight` as the smallest per-pctrank share of
the fully degraded composite, or drop the superlative and point at the code. No behaviour
change; `need` stays 4 for both markets. Fold in T35 and T36 while there.


### T38 — The ATR trail T5 was specced with is not computable [status: todo]
Priority: P3
Origin: T5
Spec: T5's spec says a trend_add alerts on "close < MA50 or ATR trail". Only the
MA50 half shipped: `Panel` (kuroshio/types.py:15) carries `close`, `volume` and
`institutional` and nothing else, so no true range — and therefore no ATR — is
reachable from any provider's output today. Both providers
(`providers/yf.py`, `providers/finmind.py`) fetch OHLCV and keep close/volume;
the fields exist upstream, they are dropped at the boundary. An ATR trail is the
better trend-break signal for a volatile name, where a fixed MA50 either whipsaws
or lags depending on the tape, so this is a real gap, not a stylistic one — it is
just a data-model change (Panel gains high/low, both providers populate it,
backtest/screening keep working) that exceeds a monitoring-rules task.
Acceptance: `Panel` carries high/low from both providers, and the trend_add rule
alerts on either the MA50 break or an ATR-multiple trail from the running high,
with a test per trigger. Until then `core/allocator/engine.py` step 3 says MA50
only, in a `ponytail:` comment naming this task.

### T39 — Thesis-intact dip setups are still the swap path's weakest incumbent [status: todo]
Priority: P1
Origin: T5
Spec: T5 fixed the alerting axis, not the ranking one, and its own opening
sentence is about the ranking one. `core/allocator/engine.py` step 4 picks
`incumbent = min(pool, key=lambda h: h.score)`, where `score` is the screener's
momentum composite: `screening/us.py:135` computes `mom_raw = (c / ma50 - 1) +
(c / ma200 - 1)` — literally MA distance — at the largest single factor weight
(0.333 of four), and TW's momentum half is close/MA20 + close/MA60 + volume
multiple. A `value_dip` bought *because* it is far under its MAs therefore scores
lowest by construction and is the name proposed for sale, even while its
invalidation price is untouched and T5's monitoring is deliberately silent about
it. The two halves now disagree: monitoring says "thesis intact", the SWAP card
says "sell this one". T5's acceptance covers alerts only, so this was logged
rather than fixed.
Acceptance: a fixture with one thesis-intact `value_dip` (score lowest, price
above `invalidation_price`) and one `trend_add` shows the swap path not choosing
the value_dip as the sell side — whether by excluding intact dip setups from the
incumbent pool, ranking on something other than the momentum score, or requiring
the setup's own invalidation before a dip position may be swapped out. Whichever
way, the reason string must say why that incumbent was picked, and the existing
`test_theme_breach_alert_and_same_theme_swap_constraint` style coverage must
still pass for holdings with no setup_type.

### T40 — Dip setups do not report a missing entry_price the way trend_add does [status: done]
Priority: P2
Origin: PR #9 R2
Spec: engine.py:126-131 builds `entry` = "entry price not recorded"; the trend_add branch
at :136 lists that gap on the coverage card, but the dip branch at :150-161 never checks
`h.entry_price`. `propose([Holding('DIP',0.05,score=0.2,setup_type='value_dip',
invalidation_price=85.0)], [], ips, 'us', prices={'DIP':84.0}, ma50={'DIP':100.0})`
returns one card ending "(entry price not recorded)" and no coverage card — the opposite
of what the trend_add path does for the identical gap. No test covers a dip setup with an
invalidation_price and entry_price=None.
Acceptance: either the dip branch lists a missing entry_price on the coverage card the
same way trend_add does, or the asymmetry is a stated rule in docs/ARCHITECTURE.md; a
test pins whichever is intended.
Update (T6 shipped): resolved the first way and for every setup at once — a missing
entry_price is now the loss-from-entry rule's gap, listed on the coverage card whatever
opened the position, pinned by test_positions_the_mae_rule_cannot_judge_are_named_not_dropped.

### T41 — Drawdown-from-entry, T5's second trend_add trigger, is not implemented [status: todo]
Priority: P2
Depends: T6
Origin: PR #9 R4
Spec: T5's spec reads "trend_add alerts on trend break (close < MA50 or ATR trail) **and**
drawdown-from-entry". Only the MA break ships: engine.py:143 `if price >= ma: continue` is
the sole trigger, and the drawdown figure is interpolated into a reason string that is
only built after the MA test already fired. A trend_add at entry 200, price 130, MA50 120
— a deep loss still above its trend — produces no card at all. T5 deferred it because the
threshold belongs to T6's forced-decision card with its own IPS key; recorded here so the
gap is a numbered deferral rather than a code comment.
Acceptance: the drawdown trigger ships with a threshold owned by T6's IPS key; until then
a trend_add at any loss above its MA50 is silent, and that is stated where the monitoring
rules are documented.
Update (T6 shipped): `caps.max_adverse_excursion_pct` exists and reads no setup_type, so
that same trend_add now gets a DECIDE card — it is no longer silent, and T41 needs no
second key. What is left is whether the *trend_add ALERT* should also fire on drawdown,
i.e. whether one position deserves both cards at a threshold it already decided on.

### T42 — Both thesis comparison boundaries are unpinned [status: todo]
Priority: P2
Origin: PR #9 R7
Spec: engine.py:152 `if price > h.invalidation_price: continue` and engine.py:143
`if price >= ma: continue`. Mutating the first to `>=` and the second to `>` each leave
the suite green, while README.md:70 promises a dip is "alerted only when it closes at or
below the invalidation price you recorded" — so the documented boundary is unpinned.
(Mutating MONITORED_SETUPS or removing entry_price from the reason string IS caught, so
the core dispatch itself is properly pinned.)
Acceptance: one case with `price == invalidation_price` asserting the alert fires and one
with `price == ma50` asserting whichever the docs say; both mutations go red.

### T43 — entry_price 0.0 falls between two disagreeing gates [status: done]
Priority: P3
Origin: PR #9 R8
Spec: engine.py:126-131 gates the entry string on truthiness (`if h.entry_price`) while
the coverage listing at :136 gates on `h.entry_price is None`, so
`Holding('Z',0.05,score=0.5,setup_type='trend_add',entry_price=0.0)` at price 90 / ma50
100 emits one ALERT reading "(entry price not recorded)" with `details['entry_price'] ==
0.0` and no coverage card. The holdings parser (cli.py:51) validates setup_type but not
entry_price sign or zero.
Acceptance: the two gates agree — either a non-positive entry_price is rejected at parse
time with a message naming the key, or both places use the same test so the position
lands on the coverage card.
Update (T6 shipped): resolved the second way — `engine._entry_price(h)` is the one gate
both rules read, and a 0.0 entry lands on the coverage card naming the value it found.
The parser still accepts it (cli.py:51 validates setup_type only).

### T44 — MA50 now skips suspension holes and can average a stale window [status: todo]
Priority: P3
Origin: PR #9 R3
Spec: the R3 fix in `core/allocator/signals.py:monitor_inputs` averages each
ticker's last `MA_TREND` *traded* closes instead of the last `MA_TREND` rows, so a
one-day suspension no longer voids MA50. The trade-off it buys: holes are skipped,
not counted, so a ticker halted for months averages 50 closes that may reach far
further back than 50 sessions, and nothing on the card says the number is stale.
The panel's own `lookback_days` bounds how far back it can reach, which is why this
is P3 and not higher. A staleness signal needs a per-ticker "sessions spanned"
number, which is the same shape as the high/low data the ATR trail needs (T38).
Acceptance: either a trend_add whose MA50 spans materially more than `MA_TREND`
calendar sessions is named on the coverage card with that reason, or the tolerance
is bounded (skip at most N holes) — pinned by a test with a long gap inside the
window.

### T45 — Coverage card's headline count is unpinned [status: done]
Priority: P3
Origin: PR #9 R11
Spec: engine.py:215 prints
`f"{len(unmonitored) + len(partial)} position(s) are not fully thesis-monitored."`.
Mutating it to `len(unmonitored)` alone leaves the suite at 145 passed:
`test_a_partially_monitored_position_is_not_also_claimed_unwatched` has one unmonitored
and one partial position and asserts both group lists and the split wording, but never
the count — so the card would read "1 position(s)" while naming two.
Acceptance: one assertion on the count in the mixed-group case; the mutation goes red.
Update (T6 shipped): done while rewriting that line —
test_a_position_watched_only_by_the_mae_rule_is_not_called_unwatched asserts the count,
and the `len(unmonitored)` mutation goes red.

### T46 — monitor_inputs' history threshold has an unpinned boundary [status: todo]
Priority: P3
Origin: PR #9 R12
Spec: signals.py:46 `if len(traded) >= MA_TREND:`. The fixtures use 60 traded and 40
traded sessions; nothing sits at exactly 50, so mutating `>=` to `>` leaves the suite at
145 passed and a ticker with exactly 50 traded sessions silently flips between monitored
and "fewer than 50 traded sessions". T42 covers the two comparisons in engine.py, not
this one — it is new code from PR #9's round-1 repair.
Acceptance: a fixture column with exactly MA_TREND traded sessions asserts it is
monitored; the mutation goes red.

### T47 — The alert card still calls the traded-session mean a 50-day moving average [status: todo]
Priority: P2
Origin: PR #9 R13
Spec: PR #9's R3 repair changed MA50 to the mean of each ticker's last 50 *traded* closes
and corrected engine.py:159 to say "fewer than 50 traded sessions", but engine.py:169-170
and :175 still say "its 50-day moving average of {ma:.2f}", and README.md:69-71 still says
"closes under its 50-day mean". After a halt those differ: a TW-shaped 82-row panel with a
31-session halt ending today yields an ma of 99.40 computed from 51 traded closes spanning
~115 calendar days, and the card calls it a 50-day moving average. signals.py's docstring
and docs/ARCHITECTURE.md:167-169 already say "traded sessions"; the user-visible strings
do not.
Also fold in (PR #9 R14 note 3): docs/ARCHITECTURE.md:158-161 and README.md:69-71 still
describe the rules as firing on "the close" ("ALERT when the close is under its 50-day
mean", "when it closes at or below the invalidation price you recorded") while the card
now deliberately refuses to call the print a close — the same claim one layer up, in the
same two files.
Acceptance: the alert card, README and ARCHITECTURE wording match what the number is
("50-session" or "the last 50 traded closes") and stop calling the print a close,
consistent with the coverage card. T44 still owns the staleness signal itself.


### T48 — Cards cannot say whether the session they read is open or closed [status: todo]
Priority: P3
Origin: PR #9 R6, R9
Spec: PR #9's round-2 repair dropped the open/closed claim from `_price_phrase`
(engine.py) — the card now reads "at 60.00 (2026-08-27 session)" and asserts nothing
about session state, because deciding it needs the market's close time in the market's
own timezone and no profile carries one. The local date is not that oracle in either
direction: 01:00 Taipei with `--market us` is mid-NYSE-session under yesterday's local
date, and 21:00 Taipei with `--market tw` is 7.5h past a close on today's. Saying
"still-open"/"closed" honestly means encoding (tz, open, close) per market profile in
`core/screening/__init__.py` and comparing `datetime.now(tz)` against the `asof`
session's close — a data-model change T5 deliberately did not make. Only do this if a
user actually wants the adjective; the session label alone is not wrong without it.
Acceptance: profiles carry a session calendar; `_price_phrase` takes the market and
says open/closed from it; tests cover a US market read from a UTC+8 clock at 01:00 and
a TW market read at 21:00, with the clock stubbed, not the local one.

### T49 — _price_phrase's no-asof branch is unpinned [status: todo]
Priority: P3
Origin: PR #9 R14 (reviewer note 1)
Spec: engine.py:33-34's `asof is None` branch is guarded by nothing — mutating it to
`return f"it closed at {price:.2f} in the still-open session"` leaves the suite at 149
passed. Not user-visible today: cli.py:357-365 leaves `prices={}` whenever `asof` stays
None, so the branch is unreachable through the CLI. But PR #9's round-2 repair changed
its text, and a library caller passing `prices=` without `asof=` would get it.
Acceptance: one case asserts the no-asof wording; the mutation goes red.

### T50 — The session-state guard rails are substring negatives [status: todo]
Priority: P2
Origin: PR #9 R14 (reviewer note 2)
Spec: the tests that keep PR #9's R6/R9 fix honest assert `"closed at" not in ...` and
`"still-open" not in ...`, so a differently-worded state claim slips straight through:
`f"at {price:.2f} ({asof} session), a finished close"` leaves the suite at 149 passed.
The guard is against two spellings, not against the class of claim.
Acceptance: a positive full-phrase equality on the price clause of `card.reason`, so any
added adjective goes red rather than only the two spellings that were shipped.


### T51 — A decided position gets the same DECIDE card on every run [status: todo]
Priority: P2
Origin: T6
Spec: nothing records that the user actually decided. A position 20% under entry emits an
identical DECIDE card every run until the holdings file changes, and the only edits that
silence it are lies (raise `entry_price`) or amputations (delete it, which also stops the
thesis rule). "No silent holding of losers" then decays into a card the user learns to
scroll past — the exact failure the Freeman-Shor discipline is about. Needs somewhere to
record the decision and when it was made (a field on `Holding`, or the ledger T10 wants
anyway), after which the card returns only when the loss deepens materially.
Acceptance: a position whose decision is recorded produces no DECIDE card at the same
loss, and a fresh one once it is materially further under water; one test per half.

### T52 — The MAE key measures this session's loss, not the worst one [status: todo]
Priority: P2
Origin: T6
Spec: `caps.max_adverse_excursion_pct` is compared against the latest session price
(`core/allocator/engine.py` step 3b), so a position that fell to -25% from entry and
recovered to -5% is never decided on, though its max adverse excursion was -25%. Latest
price vs entry equals MAE only for someone who runs `propose` on the day of the low; a
weekly runner silently misses the decisions the discipline exists to force. The true
number needs the minimum close since `entry_date` — panel history sliced per position,
the same data-model shape T38/T44 already need. The card text says what it measured
("is -20.0% from your entry price of ..."); it is the key's name that promises more.
Acceptance: either the threshold is compared against the low since `entry_date`, or the
key and docs stop calling it the max adverse excursion; a test with a recovered position
pins whichever is intended.

### T53 — DECIDE's "add" option carries no size [status: todo]
Priority: P3
Depends: T7
Origin: T6
Spec: the DECIDE card offers "add to it per the plan you opened it with" and names no
number, because nothing in the repo computes a target weight yet. T7's acceptance covers
TRIM and SWAP cards only, so the DECIDE card would be left as the one card that names an
action with no size.
Acceptance: T7's sizing also reaches the DECIDE card's add option, or the card says why
it cannot size it; one test.

### T54 — The MAE validator's bool guard is unpinned [status: todo]
Priority: P3
Origin: PR #10 R2
Spec: parser.py:123 `if isinstance(mae, bool) or not isinstance(mae, (int, float)):` is
correct but guarded by no test — tests/test_ips.py::test_validate_catches_a_mae_threshold_with_the_wrong_sign_or_type
exercises None, "-15", abc and .nan, never a boolean. Removing the bool clause leaves the
suite at 161 passed, and `max_adverse_excursion_pct: true` then reports the *range*
message instead of the type message (True == 1) — the exact T18 shape the validator's own
docstring says it avoids.
Acceptance: a case asserting `true` (and `false`) produces the "must be a number, not
bool" message and not the range message; the guard-removal mutation goes red.

### T55 — The positivity half of _entry_price is unpinned [status: todo]
Priority: P3
Origin: PR #10 R3
Spec: engine.py:44 `return h.entry_price if h.entry_price and h.entry_price > 0 else None`
and docs/ARCHITECTURE.md 3b state that a zero or negative entry_price is treated as
absent, but only 0.0 is tested. Mutating the line to drop `and h.entry_price > 0` leaves
the suite at 161 passed while `entry_price=-5.0` then produces no DECIDE, vanishes from
the coverage card entirely (it reads as fully watched), and prints "entry price -5.00,
now -1100.0% from entry" on the thesis card.
Acceptance: a case with `entry_price=-5.0` asserts no DECIDE, the coverage card naming it,
and `details['entry_price'] is None` on the thesis card; the mutation goes red.

### T56 — A quoted entry_price now crashes propose for every position [status: todo]
Priority: P2
Origin: PR #10 R5
Spec: T6's `_entry_price` gate evaluates `h.entry_price > 0` for every holding, so
`entry_price: "100.0"` in holdings.yml raises a bare `TypeError: '>' not supported
between instances of 'str' and 'int'`. Before T6 a position with no monitored setup_type
was skipped by step 3 entirely and never reached the comparison, so this widens an
existing crash surface. `_holdings_from_yaml` (cli.py:44-64) validates key names and
setup_type but never field types — the same gap T22 records for the coercion side.
Acceptance: either the holdings loader rejects a non-numeric entry_price with a message
naming the ticker and key (folding in T22), or `_entry_price` treats a non-number as
absent; one test on a quoted-price holdings file.

### T57 — Entry prices are unadjusted, provider closes are not [status: todo]
Priority: P1
Origin: PR #10 R7 (reviewer note)
Spec: providers/yf.py:52 fetches with `auto_adjust=True`, so every US price reaching
`propose` is a split/dividend-adjusted close, while `entry_price` is hand-typed into
holdings.yml and is not adjusted. Every rule that compares the two — T5's MA50 break and
invalidation breach, T6's MAE trigger and its printed drawdown — is skewed across any
split or dividend since entry, silently and in a direction nobody is told about. A 2:1
split alone puts a healthy position at -50% from entry. Adjusted closes are also not on
the cent grid, so the `ponytail:` comment at the MAE comparison ("US and TW both quote in
cents") is not true of what this code actually receives; TW is safe on the cent question
specifically (TWSE tick sizes are all multiples of 0.01), so the tick-size upgrade path
that comment names does not address the adjusted-close half.
Acceptance: entry-relative rules compare like with like — either entry prices are adjusted
onto the same basis as the panel, or the position is flagged when a corporate action has
occurred since entry_date rather than silently mis-measured; a test with a split between
entry_date and the panel's last session pins the chosen behaviour.

### T58 — The floored trigger enforces a deeper cap than the IPS names for cheap names [status: todo]
Priority: P2
Origin: PR #10 R8 (reviewer note 2)
Spec: flooring the trigger to the cent is a fixed absolute step, so for entries under about
0.07 the enforced threshold is materially deeper than the configured one: entry 0.03 at a
-15% cap enforces 0.02, i.e. -33.3%. The card prints the floored level honestly, but the
cap actually enforced is not the one the IPS names. At the extreme, entry 1e-5, or any
entry under a -99.99% cap, floors the trigger to 0.00 and the rule can never fire for any
positive price. Dissolves entirely if the comparison moves to the exact Decimal level
(branch (a) of R8's acceptance).
Acceptance: the enforced threshold equals the configured one at every entry price, or the
divergence is stated on the card and bounded; a case at entry 0.03 pins it.

### T59 — _trigger_price crashes on an absurd entry price instead of refusing it [status: todo]
Priority: P3
Origin: PR #10 R8 (reviewer note 1)
Spec: `_trigger_price` raises an uncaught `decimal.InvalidOperation` for an entry_price at
or above about 1e27 (the 28-digit default context, quantized to 0.01) rather than routing
through the loader's "not a price" path like a zero or negative entry does. Absurd input,
but the outcome is a traceback, not a card or a named coverage entry.
Acceptance: an out-of-range entry_price is refused the way a non-positive one is — named on
the coverage card, or rejected at parse time with a message naming the ticker and key.

