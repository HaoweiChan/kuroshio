"""core/allocator — challenger-vs-incumbent swap PROPOSALS.

ARCHITECTURE.md design rule #1: the engine never executes trades. Every path
through `propose()` ends in a ProposalCard (SWAP / TRIM / DECIDE / ALERT) for a human
to act on — that's both the product position ("proposals, not a bot") and the
regulatory line (advice, not discretionary execution).

v1 logic, in order: theme-budget alerts, hard-cap trims, per-setup_type thesis
monitoring, the forced decision at max adverse excursion, then challenger vs
weakest-same-or-any-theme incumbent swaps (gated by verdict floor + score
hurdle, capped at max_swaps_per_week). See
docs/ARCHITECTURE.md `core/allocator`.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from kuroshio.core.allocator.signals import MA_TREND
from kuroshio.types import Candidate, Holding, ProposalCard

# setup_types that carry a monitoring rule. "other" (and a missing setup_type) carry
# none — see the dispatch in `propose` step 3 and `signals.monitor_inputs`.
MONITORED_SETUPS = ("value_dip", "pullback_add", "trend_add")


def _price_phrase(price: float, asof: str | None) -> str:
    """How the card names the last print: the price and the session label it came from,
    and no claim about whether that session is open or closed. The panel's final row is
    a *close* only once the session is over, and nothing here knows that — it takes the
    market's close time in the market's own timezone, which no profile encodes. The
    local machine clock is not a substitute: 01:00 Taipei with `--market us` is
    mid-NYSE-session under *yesterday's* local date, and 21:00 Taipei with `--market tw`
    is 7.5h past the close under today's. So the card says neither, and the number is
    reported against the session it was read from."""
    if asof is None:
        return f"at {price:.2f}"
    return f"at {price:.2f} ({asof} session)"


def _entry_price(h) -> float | None:
    """The holding's entry price, or None when there isn't a usable one.

    One gate for both rules that read it: 0.0 and negatives are not prices — the
    loss-from-entry rule would divide by one and the reason string would report a move
    from a number the user never paid (tasks/TODO.md T43)."""
    return h.entry_price if h.entry_price and h.entry_price > 0 else None


def _trigger_price(entry_price: float, mae_pct: float) -> float:
    """The price at or below which a position is past `caps.max_adverse_excursion_pct`:
    the exact threshold level, rounded **down** to the cent.

    Exact, because binary floats are not: `6.60 * 0.85` is 5.609999999999999, so a plain
    product silently holds a position sitting on the user's own threshold, and rounding
    that product to the nearest cent trades the miss for the opposite error — half a cent
    of slop is fixed in absolute terms and therefore unbounded in percentage terms as the
    entry falls, which handed a 0.03 position at breakeven a card claiming it was past -15%.

    Down, because the trigger is a price and prices are quoted in cents: flooring can never
    put the level above the exact threshold, and no cent-quoted price can land between the
    two, so `price <= trigger` and `price <= exact level` are the same test on any price a
    market can print. It is also the number the card prints, at the precision it prints it.

    ponytail: cents, because US and TW both quote in them. A market quoted finer wants the
    profile's tick size here — never an epsilon, which is the slop this docstring is about.
    """
    exact = Decimal(str(entry_price)) * (1 + Decimal(str(mae_pct)) / 100)
    return float(exact.quantize(Decimal("0.01"), rounding=ROUND_FLOOR))


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
    asof: str | None = None,
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
    # `asof` is the session `prices` was read from (signals.monitor_inputs), so a card can
    # name it instead of calling a still-forming bar a close — see _price_phrase.
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
    # trail needs a data-model change first (tasks/TODO.md T38).
    thesis_gap: dict[str, str] = {}   # ticker -> why its setup_type's rule could not run
    # ticker -> what monitoring concluded, for the SWAP card in step 4 to quote.
    thesis_note: dict[str, str] = {}
    for h in holdings:
        if h.setup_type not in MONITORED_SETUPS:
            thesis_gap[h.ticker] = (
                f"setup_type '{h.setup_type}'" if h.setup_type else "no setup_type"
            )
            continue
        price = prices.get(h.ticker)
        if price is None:
            # the one gap the loss-from-entry rule below shares, so it is worded the same
            thesis_gap[h.ticker] = "no price for this session"
            continue
        entry_price = _entry_price(h)
        entry = (
            f"entry price {entry_price:.2f}, now {price / entry_price - 1:+.1%} from entry"
            if entry_price
            else "entry price not recorded"
        )
        at = _price_phrase(price, asof)
        if h.setup_type == "trend_add":
            ma = ma50.get(h.ticker)
            if ma is None:
                thesis_gap[h.ticker] = (
                    f"no MA50 for its trend_add — fewer than {MA_TREND} traded sessions"
                )
                continue
            if price >= ma:
                thesis_note[h.ticker] = (
                    f"its trend is intact — {at}, at or above its 50-day moving "
                    f"average of {ma:.2f}"
                )
                continue
            reason = (
                f"{h.ticker} was opened as a trend_add and the trend has broken: {at}, "
                f"below its 50-day moving average of {ma:.2f} ({entry}). "
                f"The setup that justified the position no longer holds."
            )
            details = {"ma50": ma}
        else:  # value_dip | pullback_add — the recorded level, never MA distance
            if h.invalidation_price is None:
                thesis_gap[h.ticker] = (
                    f"no invalidation_price for its {h.setup_type} — nothing to breach"
                )
                continue
            if price > h.invalidation_price:
                thesis_note[h.ticker] = (
                    f"its invalidation price of {h.invalidation_price:.2f} is not "
                    f"breached — {at}"
                )
                continue
            reason = (
                f"{h.ticker} was opened as a {h.setup_type} and its invalidation price is "
                f"breached: {at}, at or below the "
                f"{h.invalidation_price:.2f} you recorded as the level that ends the thesis "
                f"({entry})."
            )
            details = {"invalidation_price": h.invalidation_price}
        thesis_note[h.ticker] = "its thesis broke this run — see the ALERT above"
        alerts.append(ProposalCard(
            action="ALERT",
            reason=reason,
            details={
                "ticker": h.ticker, "setup_type": h.setup_type,
                "entry_price": entry_price, "price": price, "asof": asof, **details,
            },
        ))

    # 3b. max adverse excursion (Freeman-Shor): a loss this size forces a decision, and
    # dispatches on nothing — any position with an entry price can be far enough under
    # water, whatever setup opened it, or none. Built after the loop above so it can quote
    # what that loop concluded about the same ticker instead of talking past it.
    # ponytail: this session's price against entry, not the worst price since entry — a
    # position that fell past the threshold and recovered is not decided on. Equal to the
    # real excursion only for someone who runs propose the day of the low; the low itself
    # needs panel history sliced from entry_date (tasks/TODO.md T52).
    mae_gap: dict[str, str] = {}   # ticker -> why the loss-from-entry rule could not run
    decided: dict[str, str] = {}   # ticker -> its loss, for the SWAP card in step 4 to quote
    mae_pct = ips.caps.max_adverse_excursion_pct
    decisions: list[ProposalCard] = []
    for h in holdings:
        price, entry_price = prices.get(h.ticker), _entry_price(h)
        if price is None:
            mae_gap[h.ticker] = "no price for this session"
            continue
        if entry_price is None:
            mae_gap[h.ticker] = (
                "no entry_price" if h.entry_price is None
                else f"entry_price {h.entry_price} is not a price"
            ) + ", so the loss from entry is not watched"
            continue
        trigger = _trigger_price(entry_price, mae_pct)
        if price > trigger:
            continue
        note = thesis_note.get(h.ticker)
        decided[h.ticker] = f"{price / entry_price - 1:+.1%}"
        decisions.append(ProposalCard(
            action="DECIDE",
            reason=(
                f"{h.ticker} is {price / entry_price - 1:+.1%} from your entry price of "
                f"{entry_price:.2f}, {_price_phrase(price, asof)} — at or past your IPS max "
                f"adverse excursion of {mae_pct:.1f}%, the {trigger:.2f} level from that "
                f"entry. Decide: kill it, add to it per the plan you opened it with, or "
                f"rewrite the thesis and record the new one. Holding it unchanged is not "
                f"one of the three."
                + (
                    f" Monitoring checked {h.ticker} this run: it is a {h.setup_type} "
                    f"and {note}." if note else ""
                )
            ),
            ips_clauses=["caps.max_adverse_excursion_pct"],
            details={
                "ticker": h.ticker, "entry_price": entry_price, "price": price, "asof": asof,
                "drawdown": price / entry_price - 1, "threshold_pct": mae_pct,
                "trigger_price": trigger,
            },
        ))

    # 3c. coverage. Two rules watch a position — its setup_type's and the loss-from-entry
    # one — so a position is fully watched, partly watched, or watched by neither, and the
    # three say different things. A partially-monitored position is not an unwatched one:
    # the same run may well have alerted on it, and claiming "this run says nothing about
    # it either way" over both groups made two cards contradict each other about one
    # ticker. Emitted only when something is actually being watched, so a holdings file
    # with no setup_type and no entry_price anywhere gets its cards unchanged.
    unmonitored: list[str] = []   # nothing at all is watching these
    partial: list[str] = []       # watched, but not on every axis they have
    watching_anything = False
    for h in holdings:
        why = [g for g in (thesis_gap.get(h.ticker), mae_gap.get(h.ticker)) if g]
        watching_anything |= len(why) < 2
        if not why:
            continue
        # dict.fromkeys: both rules read the session price, so a position without one
        # states that reason once.
        item = f"{h.ticker} ({'; '.join(dict.fromkeys(why))})"
        (partial if len(why) == 1 else unmonitored).append(item)
    if (unmonitored or partial) and watching_anything:
        said = [f"{len(unmonitored) + len(partial)} position(s) are not fully monitored."]
        if unmonitored:
            said.append(
                f"Nothing is watching {', '.join(unmonitored)}: the thesis rule dispatches "
                f"on setup_type and the loss-from-entry rule needs an entry price, and a "
                f"position missing what a rule reads gets no check from it — this run says "
                f"nothing about those either way."
            )
        if partial:
            said.append(
                f"Partly watched: one of the two rules ran on each of these this session "
                f"and the other could not — {', '.join(partial)}."
            )
        alerts.append(ProposalCard(
            action="ALERT",
            reason=" ".join(said),
            details={
                "unmonitored": [u.split(" (")[0] for u in unmonitored],
                "partially_monitored": [u.split(" (")[0] for u in partial],
            },
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
            # The bridge between step 3 and step 4: the ranking is a momentum composite
            # and does not read setup_type (tasks/TODO.md T39), so a thesis-intact
            # value_dip can still be the weakest incumbent. Say so on the card rather
            # than letting both halves of the run go silent about the same position.
            note = thesis_note.get(incumbent.ticker)
            bridge = (
                f" Monitoring checked {incumbent.ticker} this run: it is a "
                f"{incumbent.setup_type} and {note}."
                if note else ""
            )
            # Selling a position this run already forced a decision on is one of that
            # card's three options, not a fourth: without this the same run told the user
            # to add to it per plan and to sell it, with neither card naming the other.
            if incumbent.ticker in decided:
                bridge += (
                    f" {incumbent.ticker} is also {decided[incumbent.ticker]} from its "
                    f"entry price and has a DECIDE card above: this SWAP is the 'kill it' "
                    f"option on that card, not a fourth one."
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
                    f"'{verdict}', at or above your floor of '{floor}'.{bridge}{disclosure}"
                ),
                ips_clauses=["turnover.hurdle", "turnover.verdict_floor", f"friction.{friction_field}"],
                score_gap=gap,
                friction_pct=friction_pct,
                details={
                    "challenger_score": c.final_score,
                    "incumbent_score": incumbent.score,
                    "verdict": verdict,
                    "auto_scored": auto,
                    "incumbent_setup_type": incumbent.setup_type,
                    "incumbent_thesis": note,
                    "incumbent_decided": incumbent.ticker in decided,
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

    # decisions after alerts: a DECIDE quotes the thesis ALERT above it ("see the ALERT
    # above") when the same run broke that position's thesis.
    return alerts + decisions + trims + kept
