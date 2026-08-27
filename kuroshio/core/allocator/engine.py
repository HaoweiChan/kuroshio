"""core/allocator — challenger-vs-incumbent swap PROPOSALS.

ARCHITECTURE.md design rule #1: the engine never executes trades. Every path
through `propose()` ends in a ProposalCard (SWAP / TRIM / ALERT) for a human
to act on — that's both the product position ("proposals, not a bot") and the
regulatory line (advice, not discretionary execution).

v1 logic, in order: theme-budget alerts, hard-cap trims, per-setup_type thesis
monitoring, then challenger vs weakest-same-or-any-theme incumbent swaps (gated
by verdict floor + score hurdle, capped at max_swaps_per_week). See
docs/ARCHITECTURE.md `core/allocator`.
"""

from __future__ import annotations

from kuroshio.types import Candidate, Holding, ProposalCard

# setup_types that carry a monitoring rule. "other" (and a missing setup_type) carry
# none — see the dispatch in `propose` step 3 and `signals.monitor_inputs`.
MONITORED_SETUPS = ("value_dip", "pullback_add", "trend_add")


def swap_hurdle(ips, market: str) -> tuple[float, float, str]:
    """The bar a swap's score gap must clear, in score space: the IPS turnover hurdle
    plus round-trip friction. friction_pct is a percentage (0.585 == 0.585%) while the
    hurdle and the gap live in score space (0..1), so /100 converts it to the
    score-equivalent ARCHITECTURE.md asks for. Returns (bar, friction_pct, ips field).

    cli.py's auto-fill guard keys off the same number — a percentile pool too coarse to
    ever produce a gap under this bar cannot be ranked honestly — so the friction math
    stays in one place."""
    field = "tw_roundtrip_pct" if market.lower() == "tw" else "us_roundtrip_pct"
    friction_pct = getattr(ips.friction, field)
    return ips.turnover.hurdle + friction_pct / 100, friction_pct, field


def propose(
    holdings: list[Holding],
    challengers: list[Candidate],
    ips,
    market: str,
    verdicts: dict[str, str] | None = None,
    swaps_this_week: int = 0,
    themes: dict[str, str] | None = None,
    auto_scored: dict[str, int] | None = None,
    prices: dict[str, float] | None = None,
    ma50: dict[str, float] | None = None,
) -> list[ProposalCard]:
    # lazy: kuroshio.core.ips is a sibling module developed in parallel — importing
    # here (not at module load) keeps this package importable regardless of ordering.
    from kuroshio.core.ips.schema import verdict_at_least

    verdicts = verdicts or {}
    themes = themes or {}
    # ticker -> size of the pctrank pool its score was auto-filled from. pctrank pins
    # its extremes to 0.000/1.000 however tightly the factors cluster, so such a gap is
    # a rank distance inside the user's own files, not a `kuroshio screen` difference —
    # the card says so rather than printing the number bare (see cli.py:_score_missing).
    auto_scored = auto_scored or {}
    # last close and 50-day mean close per ticker, computed by the caller from a panel
    # (allocator.signals.monitor_inputs) — core/allocator takes no panel and no provider.
    prices = prices or {}
    ma50 = ma50 or {}
    theme_cap = ips.caps.theme_pct / 100
    hard_cap = ips.caps.position_hard_pct / 100
    exempt = {(e.ticker, e.cap) for e in ips.caps.exemptions}
    theme_pct_exempt = {e.ticker for e in ips.caps.exemptions if e.cap == "theme_pct"}

    alerts: list[ProposalCard] = []
    trims: list[ProposalCard] = []

    # 1. theme budgets — effective exposure = weight x leverage, summed per theme.
    # Fix 4: a `theme_pct` exemption (e.g. RULES AM4d's 群創/面板 carve-out) removes
    # that ticker's exposure from its theme's total, same as the hard-cap TRIM step
    # already does for `position_hard_pct` exemptions below.
    exposures: dict[str, float] = {}
    for h in holdings:
        if h.theme is None or h.ticker in theme_pct_exempt:
            continue
        exposures[h.theme] = exposures.get(h.theme, 0.0) + h.weight * h.leverage
    breached = {t for t, exp in exposures.items() if exp > theme_cap}
    for theme in sorted(breached):
        exp = exposures[theme]
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                f"Theme '{theme}' effective exposure is {exp:.1%}, above your IPS theme "
                f"budget of {theme_cap:.1%}. Challengers tagged to this theme may only "
                f"swap against incumbents in the same theme until it's back under budget."
            ),
            ips_clauses=["caps.theme_pct"],
            details={"theme": theme, "exposure": exp, "cap": theme_cap},
        ))

    # 2. hard-cap breaches -> TRIM, unless explicitly exempted.
    for h in holdings:
        if h.weight <= hard_cap or (h.ticker, "position_hard_pct") in exempt:
            continue
        trims.append(ProposalCard(
            action="TRIM",
            sell=h.ticker,
            reason=(
                f"{h.ticker} is {h.weight:.1%} of NAV, above your IPS hard cap of "
                f"{hard_cap:.1%} per name. Trim it back under the ceiling."
            ),
            ips_clauses=["caps.position_hard_pct"],
            details={"weight": h.weight, "cap": hard_cap},
        ))

    # 3. thesis monitoring — dispatch on setup_type. A value_dip is *supposed* to look
    # weak against its moving averages: that is the setup, not a broken thesis, so only
    # the invalidation_price the user recorded ends it. A trend_add is the opposite —
    # the trend is the thesis, so a close under the 50-day mean is the exit signal.
    # ponytail: MA50 only. Panel carries close/volume, no high/low, so the spec's ATR
    # trail needs a data-model change first (tasks/TODO.md T38). Drawdown from entry is
    # reported on the card, not thresholded: the loss-from-entry threshold is T6's, with
    # its own IPS key, and two thresholds would be one too many.
    unmonitored: list[str] = []
    for h in holdings:
        if h.setup_type not in MONITORED_SETUPS:
            why = f"setup_type '{h.setup_type}'" if h.setup_type else "no setup_type"
            unmonitored.append(f"{h.ticker} ({why})")
            continue
        price = prices.get(h.ticker)
        if price is None:
            unmonitored.append(f"{h.ticker} ({h.setup_type}, no price for this session)")
            continue
        entry = (
            f"entry price {h.entry_price:.2f}, now {price / h.entry_price - 1:+.1%} from entry"
            if h.entry_price  # 0.0 is not a price: unrecorded beats dividing by it
            else "entry price not recorded"
        )
        if h.setup_type == "trend_add":
            ma = ma50.get(h.ticker)
            if ma is None:
                unmonitored.append(f"{h.ticker} (trend_add, no MA50 — too little price history)")
                continue
            if h.entry_price is None:
                unmonitored.append(
                    f"{h.ticker} (trend_add, no entry_price — the MA50 break is watched, "
                    f"drawdown from entry is not)"
                )
            if price >= ma:
                continue
            reason = (
                f"{h.ticker} was opened as a trend_add and the trend has broken: it closed "
                f"at {price:.2f}, below its 50-day moving average of {ma:.2f} ({entry}). "
                f"The setup that justified the position no longer holds."
            )
            details = {"ma50": ma}
        else:  # value_dip | pullback_add — the recorded level, never MA distance
            if h.invalidation_price is None:
                unmonitored.append(
                    f"{h.ticker} ({h.setup_type}, no invalidation_price — nothing to breach)"
                )
                continue
            if price > h.invalidation_price:
                continue
            reason = (
                f"{h.ticker} was opened as a {h.setup_type} and its invalidation price is "
                f"breached: it closed at {price:.2f}, at or below the "
                f"{h.invalidation_price:.2f} you recorded as the level that ends the thesis "
                f"({entry})."
            )
            details = {"invalidation_price": h.invalidation_price}
        alerts.append(ProposalCard(
            action="ALERT",
            reason=reason,
            details={
                "ticker": h.ticker, "setup_type": h.setup_type,
                "entry_price": h.entry_price, "price": price, **details,
            },
        ))
    # Only when the portfolio is actually using thesis monitoring: with no setup_type
    # anywhere, no position can look watched, and a pre-T3 holdings file gets its cards
    # unchanged. Mixed coverage is the dangerous case — that is what this names.
    if unmonitored and any(h.setup_type in MONITORED_SETUPS for h in holdings):
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                f"{len(unmonitored)} position(s) are not fully thesis-monitored: "
                f"{', '.join(unmonitored)}. Monitoring dispatches on setup_type, so a "
                f"position missing the fields its rule reads is not being watched for a "
                f"thesis break — the rest of this run says nothing about it either way."
            ),
            details={"unmonitored": [u.split(" (")[0] for u in unmonitored]},
        ))

    # 4. challenger vs incumbent.
    held = {h.ticker for h in holdings}
    scored = [h for h in holdings if h.score is not None]
    swaps: list[ProposalCard] = []
    if not scored:
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                "No current holding has a screener score, so no incumbent can be "
                "objectively ranked weakest — run the screener before evaluating swaps."
            ),
        ))
    else:
        used: set[str] = set()
        floor = ips.turnover.verdict_floor
        hurdle, friction_pct, friction_field = swap_hurdle(ips, market)
        # strongest challenger picks first — caller order must not decide who
        # gets the weakest incumbent
        for c in sorted(challengers, key=lambda c: c.final_score, reverse=True):
            if c.ticker in held:
                continue
            verdict = verdicts.get(c.ticker, "neutral")
            if not verdict_at_least(verdict, floor):
                continue
            theme = themes.get(c.ticker)
            same_theme_only = theme in breached
            pool = [h for h in scored if h.ticker not in used and (not same_theme_only or h.theme == theme)]
            if not pool:
                continue
            incumbent = min(pool, key=lambda h: h.score)
            gap = c.final_score - incumbent.score
            if gap < hurdle:
                continue
            used.add(incumbent.ticker)
            auto = [t for t in (c.ticker, incumbent.ticker) if t in auto_scored]
            disclosure = ""
            if len(auto) == 2:
                disclosure = (
                    f" Auto-filled score(s): {', '.join(auto)} — a percentile rank among "
                    f"the {auto_scored[auto[0]]} names in your own files, so this gap is a "
                    f"rank distance within that pool, not a difference in screener scores."
                )
            elif auto:
                # One operand is a percentile in that pool and the other is a hand-typed
                # number that was never put on it, so the subtraction spans two scales and
                # is not a rank distance in either (R14).
                hand = c.ticker if auto[0] == incumbent.ticker else incumbent.ticker
                disclosure = (
                    f" Auto-filled score(s): {auto[0]} — a percentile rank among the "
                    f"{auto_scored[auto[0]]} names in your own files. {hand}'s score is "
                    f"hand-typed and not on that scale, so this gap subtracts two different "
                    f"scales: it is not a rank distance, and {hand}'s own rank in that pool "
                    f"would give a different number."
                )
            swaps.append(ProposalCard(
                action="SWAP",
                sell=incumbent.ticker,
                buy=c.ticker,
                reason=(
                    f"Challenger {c.ticker} scores {c.final_score:.3f} vs incumbent "
                    f"{incumbent.ticker}'s {incumbent.score:.3f} — a gap of {gap:.3f}, above "
                    f"your IPS turnover hurdle of {ips.turnover.hurdle:.3f} plus estimated "
                    f"round-trip friction of {friction_pct:.3f}%. {c.ticker}'s verdict is "
                    f"'{verdict}', at or above your floor of '{floor}'.{disclosure}"
                ),
                ips_clauses=["turnover.hurdle", "turnover.verdict_floor", f"friction.{friction_field}"],
                score_gap=gap,
                friction_pct=friction_pct,
                details={
                    "challenger_score": c.final_score,
                    "incumbent_score": incumbent.score,
                    "verdict": verdict,
                    "auto_scored": auto,
                },
            ))

    # 5. order + weekly turnover cap.
    swaps.sort(key=lambda card: card.score_gap, reverse=True)
    room = max(ips.turnover.max_swaps_per_week - swaps_this_week, 0)
    kept, suppressed = swaps[:room], swaps[room:]
    if suppressed:
        kept.append(ProposalCard(
            action="ALERT",
            reason=(
                f"{len(suppressed)} additional swap(s) cleared the hurdle but were suppressed "
                f"by your IPS turnover limit of {ips.turnover.max_swaps_per_week} swaps/week "
                f"({swaps_this_week} already made this week)."
            ),
            ips_clauses=["turnover.max_swaps_per_week"],
            details={"suppressed_count": len(suppressed)},
        ))

    return alerts + trims + kept
