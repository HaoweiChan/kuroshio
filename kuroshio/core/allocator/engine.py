"""core/allocator — challenger-vs-incumbent swap PROPOSALS.

ARCHITECTURE.md design rule #1: the engine never executes trades. Every path
through `propose()` ends in a ProposalCard (SWAP / TRIM / SCALE / DECIDE / ALERT) for a
human to act on — that's both the product position ("proposals, not a bot") and the
regulatory line (advice, not discretionary execution).

v1 logic, in order: theme-budget alerts, hard-cap trims, a book-wide vol-target SCALE,
per-setup_type thesis monitoring, the forced decision at max adverse excursion, then
challenger vs weakest-same-or-any-theme incumbent swaps (gated by verdict floor + score
hurdle, capped at max_swaps_per_week). See
docs/ARCHITECTURE.md `core/allocator`.
"""

from __future__ import annotations

from decimal import Decimal

from kuroshio.core.allocator.signals import BOOK_VOL_WINDOW, MA_TREND
from kuroshio.types import Candidate, Holding, ProposalCard

# setup_types that carry a monitoring rule. "other" (and a missing setup_type) carry
# none — see the dispatch in `propose` step 3 and `signals.monitor_inputs`.
MONITORED_SETUPS = ("value_dip", "pullback_add", "trend_add")
# setup_types whose invalidation price ratchets up behind the tape — see `propose` step
# 3a. A value_dip is not one: its level is a valuation thesis the user wrote down, not a
# distance from a high the position has not made yet.
TRAILED_SETUPS = ("trend_add", "pullback_add")


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


def _past_threshold(price: float, entry_price: float, mae_pct: float) -> bool:
    """Is `price` at or past `mae_pct` from `entry_price`?

    Exact decimal arithmetic, and no rounding of any operand. The binary product is not
    the level — `6.60 * 0.85` is 5.609999999999999, which holds a position sitting exactly
    on the user's own threshold — and snapping that level to the cent grid trades the miss
    for the opposite error: `propose` is handed the panel's float64 closes, not prices a
    market printed (`allocator/signals.py`, and `providers/yf.py` fetches with
    auto_adjust=True), so any price between two cents is misjudged in whichever direction
    the level was snapped.

    `Decimal(str(x))` on all three, never `Decimal(x)`: str gives the shortest decimal that
    round-trips the float, i.e. the number as written and as printed, while the binary
    expansion of 6.6 is 6.5999999999999996447... and reintroduces the artifact above.
    """
    return Decimal(str(price)) <= Decimal(str(entry_price)) * (1 + Decimal(str(mae_pct)) / 100)


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


def target_weight(ips, h) -> tuple[float, str, str]:
    """The size policy allows one position: the weight as a fraction of NAV, the IPS
    clause that set it, and why in words for the card to quote.

    Two caps, and the smaller binds. (a) `caps.position_pct`, the flat base every
    position starts from. (b) percent-risk: `caps.risk_budget_pct` of NAV risked over the
    distance from the entry price to the invalidation price the user recorded. Shares are
    risk x NAV / (entry - invalidation), so the weight is risk x entry / (entry -
    invalidation) — NAV cancels, which is why `propose` needs no portfolio value to size
    anything. (c), inverse-vol parity, is not here: it needs a vol estimate and `propose`
    takes no panel (docs/PORTFOLIO-PLAN.md phase 3).

    An invalidation at or above the entry price is not a stop, and is treated as absent
    rather than sized on: its distance is zero or negative, which would divide by zero or
    cap the position at a negative weight.

    `position_hard_pct` is deliberately not in the min. `validate` holds `position_pct` at
    or under it, so it could only bind on an IPS that was never validated — and the hard
    cap is the ceiling the TRIM card is already about, not a sizing input.
    """
    base = ips.caps.position_pct / 100
    entry, invalidation = _entry_price(h), h.invalidation_price
    if entry is None or invalidation is None or invalidation >= entry:
        return base, "caps.position_pct", (
            f"your IPS base position cap of {ips.caps.position_pct:.1f}% of NAV — without "
            f"an entry price and an invalidation price below it, the percent-risk cap has "
            f"no distance to size against"
        )
    risk = ips.caps.risk_budget_pct / 100 * entry / (entry - invalidation)
    if risk < base:
        return risk, "caps.risk_budget_pct", (
            f"the percent-risk cap binds: {ips.caps.risk_budget_pct:.2f}% of NAV risked "
            f"over the {entry:.2f} entry to {invalidation:.2f} invalidation distance is "
            f"tighter than your {ips.caps.position_pct:.1f}% base position cap"
        )
    return base, "caps.position_pct", (
        f"your IPS base position cap of {ips.caps.position_pct:.1f}% of NAV, tighter than "
        f"the {risk:.1%} the percent-risk cap allows"
    )


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
    pool_name: str = "your own files",
    book_vol: float | None = None,
    *,
    running_high: dict[str, float] | None = None,
    atr14: dict[str, float] | None = None,
    min_close: dict[str, float] | None = None,
    last_stop: dict[str, float] | None = None,
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
    # the same seam, for the stop ratchet and the max-adverse-excursion rule: running high
    # and minimum close since each holding's entry_date, and ATR14, from
    # allocator.signals.trail_inputs. Empty = those rules degrade to what they did before
    # TASK-11 (the recorded level, and this session's price).
    running_high = running_high or {}
    atr14 = atr14 or {}
    min_close = min_close or {}
    # the newest stop an earlier run's ratchet logged per ticker (cli reads it back from
    # ledger.STOPS — core/allocator imports no ledger, same rule as the panel). Empty =
    # the ratchet only knows the recorded level, which is a run with no history yet.
    last_stop = last_stop or {}
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
    # a theme named in caps.theme_caps lives under its own budget; the rest under theme_pct
    def cap_for(theme: str) -> tuple[float, str]:
        if theme in ips.caps.theme_caps:
            return ips.caps.theme_caps[theme] / 100, f"caps.theme_caps.{theme}"
        return theme_cap, "caps.theme_pct"
    breached = {t for t, exp in exposures.items() if exp > cap_for(t)[0]}
    for theme in sorted(breached):
        exp = exposures[theme]
        cap, clause = cap_for(theme)
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                f"Theme '{theme}' effective exposure is {exp:.1%}, above your IPS theme "
                f"budget of {cap:.1%}. Challengers tagged to this theme may only "
                f"swap against incumbents in the same theme until it's back under budget."
            ),
            ips_clauses=[clause],
            details={"theme": theme, "exposure": exp, "cap": cap},
        ))

    # 2. hard-cap breaches -> TRIM, unless explicitly exempted.
    for h in holdings:
        if h.weight <= hard_cap or (h.ticker, "position_hard_pct") in exempt:
            continue
        # "back under the ceiling" is not a number: the hard cap says where the position
        # stops being allowed, and target_weight says where policy wanted it in the first
        # place, which is the one the user can act on.
        target, cap_clause, why = target_weight(ips, h)
        trims.append(ProposalCard(
            action="TRIM",
            sell=h.ticker,
            reason=(
                f"{h.ticker} is {h.weight:.1%} of NAV, above your IPS hard cap of "
                f"{hard_cap:.1%} per name. Trim it to {target:.1%} of NAV — {why}."
            ),
            ips_clauses=["caps.position_hard_pct", cap_clause],
            details={
                "weight": h.weight, "cap": hard_cap,
                "target_weight": target, "binding_cap": cap_clause,
            },
        ))

    # 2b. book vol target — one book-wide SCALE, never a card that levers up (scale is
    # clamped to at most 1.0 by signals.book_vol/simulate's own arithmetic, but the target
    # check below (book_vol > target) already means this branch only ever cuts).
    scale_cards: list[ProposalCard] = []
    target = ips.caps.book_vol_target_pct
    if target is not None and book_vol is not None and book_vol > target:
        scale = target / book_vol
        scale_cards.append(ProposalCard(
            action="SCALE",
            reason=(
                f"The book's trailing {BOOK_VOL_WINDOW}-session realized volatility is "
                f"{book_vol:.1f}% (annualized), above your IPS book vol target of "
                f"{target:.1f}%. Scale gross exposure to {scale:.0%} (sell "
                f"{1 - scale:.0%} of every position pro rata) to bring the book back "
                f"to target."
            ),
            ips_clauses=["caps.book_vol_target_pct"],
            details={
                "book_vol_pct": book_vol, "target_pct": target,
                "window": BOOK_VOL_WINDOW, "scale": scale,
            },
        ))

    # 3. thesis monitoring — dispatch on setup_type. A value_dip is *supposed* to look
    # weak against its moving averages: that is the setup, not a broken thesis, so only
    # the invalidation_price the user recorded ends it. A trend_add is the opposite —
    # the trend is the thesis, so a close under the 50-day mean is the exit signal.
    #
    # 3a. the stop ratchet (TASK-11), run before the dispatch that reads the level it
    # sets. A trend_add trails always — the trend is the thesis, so the tape draws the
    # only level it ever had. A pullback_add trails only once the running high has cleared
    # entry + 2R: before that the position is still inside the pullback it was bought in,
    # and a trail there stops it out on the setup itself. The level never moves down,
    # which is what makes this a ratchet and not a recomputation.
    # "Never down" is a claim across runs, so the level a run has to beat is the higher of
    # what the user recorded and what an earlier run already ratcheted to (`last_stop`,
    # read back from the stop ledger by the caller). Comparing only against the recorded
    # level let a widening ATR14 under an unchanged high walk the stop back down.
    live_stop: dict[str, float] = {}   # ticker -> the invalidation price this run watches
    for h in holdings:
        levels = [x for x in (h.invalidation_price, last_stop.get(h.ticker)) if x is not None]
        if levels:
            live_stop[h.ticker] = max(levels)
    moved: set[str] = set()   # tickers this run's ratchet actually raised
    for h in holdings:
        if h.setup_type not in TRAILED_SETUPS:
            continue
        peak, atr = running_high.get(h.ticker), atr14.get(h.ticker)
        if peak is None or atr is None:
            # no entry_date to measure a running high from, or a panel with no high/low
            # and so no true range: nothing to trail from, and the recorded level stands.
            continue
        was, entry_price = live_stop.get(h.ticker), _entry_price(h)
        if h.setup_type == "pullback_add":
            # R is the entry-to-invalidation distance, so without both there is no 2R gate
            # to clear and the pullback keeps the level the user recorded.
            recorded = h.invalidation_price
            if entry_price is None or recorded is None or recorded >= entry_price:
                continue
            if peak < entry_price + 2 * (entry_price - recorded):
                continue
        trail = peak - ips.caps.trail_atr_mult * atr
        if was is not None and trail <= was:
            continue
        live_stop[h.ticker] = trail
        moved.add(h.ticker)
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                f"{h.ticker}'s stop ratchets up to {trail:.2f}: its running high since "
                f"{h.entry_date} is {peak:.2f}, and {ips.caps.trail_atr_mult:g}x its ATR14 "
                f"of {atr:.2f} below that sits above "
                + (
                    f"the {was:.2f} it was already watching."
                    if was is not None
                    else "the level it had — you recorded none."
                )
                + f" Monitoring watches {trail:.2f} from here, and a ratcheted stop never "
                f"moves back down — later runs read this level back from the stop ledger."
            ),
            ips_clauses=["caps.trail_atr_mult"],
            details={
                "ticker": h.ticker, "setup_type": h.setup_type, "ratchet": True,
                "old_invalidation": was, "new_invalidation": trail,
                "running_high": peak, "atr14": atr, "asof": asof,
            },
        ))

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
        stop = live_stop.get(h.ticker)
        # how a card names the level: the user's own words for it, or the trail's — and
        # the ALERT is only "above" when this run is the one that moved it.
        level = "" if stop is None else (
            f"{stop:.2f} its stop has ratcheted up to (see the ALERT above)"
            if h.ticker in moved
            else f"{stop:.2f} its stop had already ratcheted up to on an earlier run"
            if stop != h.invalidation_price
            else f"{stop:.2f} you recorded as the level that ends the thesis"
        )
        if h.setup_type == "trend_add" and (stop is None or price > stop):
            # the trend half of the rule; the trailed stop below is the drawdown half
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
        elif h.setup_type == "trend_add":
            reason = (
                f"{h.ticker} was opened as a trend_add and its trailing stop is breached: "
                f"{at}, at or below the {level} ({entry}). "
                f"The setup that justified the position no longer holds."
            )
            details = {"invalidation_price": stop}
        else:  # value_dip | pullback_add — the recorded level, never MA distance
            if stop is None:
                thesis_gap[h.ticker] = (
                    f"no invalidation_price for its {h.setup_type} — nothing to breach"
                )
                continue
            if price > stop:
                thesis_note[h.ticker] = (
                    f"its invalidation price of {stop:.2f} is not breached — {at}"
                )
                continue
            reason = (
                f"{h.ticker} was opened as a {h.setup_type} and its invalidation price is "
                f"breached: {at}, at or below the {level} ({entry})."
            )
            details = {"invalidation_price": stop}
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
    # The excursion is the worst *close* since entry_date (signals.trail_inputs), not this
    # session's price: a position that fell to -25% and recovered to -5% made the decision
    # the key exists to force, and running propose weekly must not miss it (TASK-11 #4).
    # A holding with no entry_date has no such window, and falls back to today's price.
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
        low = min_close.get(h.ticker)
        worst = price if low is None else min(price, low)
        if not _past_threshold(worst, entry_price, mae_pct):
            continue
        note = thesis_note.get(h.ticker)
        decided[h.ticker] = f"{worst / entry_price - 1:+.1%}"
        # the card states what the rule read: the low when the position has recovered off
        # it, and this session's print when the low *is* this session's print.
        lead = (
            f"{h.ticker} fell to {worst / entry_price - 1:+.1%} from your entry price of "
            f"{entry_price:.2f} — its lowest close since {h.entry_date} was {worst:.2f}, "
            f"and it is back {_price_phrase(price, asof)}"
            if worst < price else
            f"{h.ticker} is {worst / entry_price - 1:+.1%} from your entry price of "
            f"{entry_price:.2f}, {_price_phrase(price, asof)}"
        )
        decisions.append(ProposalCard(
            action="DECIDE",
            reason=(
                f"{lead} — at or past your IPS max "
                f"adverse excursion of {mae_pct:.1f}%. "
                f"Decide: kill it, add to it per the plan you opened it with, or "
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
                "drawdown": worst / entry_price - 1, "threshold_pct": mae_pct,
                # only when the rule had one: the card's details are the numbers it read
                **({"min_close": worst} if low is not None else {}),
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
                    f"the {auto_scored[auto[0]]} names in {pool_name}, so this gap is a "
                    f"rank distance within that pool, not a difference in screener scores."
                )
            elif auto:
                # One operand is a percentile in that pool and the other is a hand-typed
                # number that was never put on it, so the subtraction spans two scales and
                # is not a rank distance in either (R14).
                hand = c.ticker if auto[0] == incumbent.ticker else incumbent.ticker
                disclosure = (
                    f" Auto-filled score(s): {auto[0]} — a percentile rank among the "
                    f"{auto_scored[auto[0]]} names in {pool_name}. {hand}'s score is "
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
            # Sizing on a SWAP is the incumbent's, and the card says whose it is. The buy
            # is a name the user has not opened: a Candidate carries no entry or
            # invalidation price (cli.py builds it from a screen, not from a plan), so the
            # percent-risk cap has nothing to read on that side. What can be sized is the
            # slot being freed.
            target, cap_clause, why = target_weight(ips, incumbent)
            sizing = (
                f" Sizing is {incumbent.ticker}'s: its target weight is {target:.1%} of "
                f"NAV — {why}. {c.ticker} has no entry or invalidation price on file, so "
                f"nothing here sizes the buy — record them and it gets the same caps."
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
                    f"'{verdict}', at or above your floor of '{floor}'."
                    f"{sizing}{bridge}{disclosure}"
                ),
                ips_clauses=[
                    "turnover.hurdle", "turnover.verdict_floor",
                    f"friction.{friction_field}", cap_clause,
                ],
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
                    "target_weight": target,
                    "binding_cap": cap_clause,
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
    # above") when the same run broke that position's thesis. SCALE goes after TRIMs
    # (both are cap enforcement) and before the challenger-driven SWAP cards.
    return alerts + decisions + trims + scale_cards + kept
