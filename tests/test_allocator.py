import datetime
from itertools import product

import pytest

from kuroshio.core.allocator import propose
from kuroshio.core.ips import IPS, validate
from kuroshio.core.ips.schema import CapExemption
from kuroshio.types import Candidate, Holding, Panel, ProposalCard


def make_ips(**overrides) -> IPS:
    ips = IPS()
    for path, value in overrides.items():
        obj = ips
        parts = path.split(".")
        for p in parts[:-1]:
            obj = getattr(obj, p)
        setattr(obj, parts[-1], value)
    return ips


def cand(ticker, final_score, **kw):
    return Candidate(ticker=ticker, date="2026-07-12", rank=1, final_score=final_score, **kw)


def test_theme_breach_alert_and_same_theme_swap_constraint():
    # AI theme at 2x0.15 = 30% effective exposure, over a 20% cap.
    holdings = [
        Holding(ticker="AAA", weight=0.15, theme="ai", score=0.85),  # weakest ai incumbent
        Holding(ticker="BBB", weight=0.15, theme="ai", score=0.90),
        Holding(ticker="CCC", weight=0.05, theme=None, score=0.10),  # global weakest, non-ai
    ]
    # challenger tagged "ai" clears the hurdle against the (much weaker) global-weakest
    # incumbent CCC, but not against the weakest *same-theme* incumbent AAA — the theme
    # constraint must force it to be judged against AAA and rejected.
    challengers = [cand("XXX", final_score=0.95)]
    ips = make_ips(**{"turnover.hurdle": 0.15})

    cards = propose(holdings, challengers, ips, "us", themes={"XXX": "ai"})

    alert = [c for c in cards if c.action == "ALERT" and c.details.get("theme") == "ai"]
    assert len(alert) == 1
    assert alert[0].details["exposure"] > alert[0].details["cap"]

    # must NOT swap XXX against CCC (different theme), even though CCC is weaker overall.
    swaps = [c for c in cards if c.action == "SWAP"]
    assert all(c.sell != "CCC" for c in swaps)
    assert swaps == []  # no ai incumbent scored low enough to clear the 0.15 hurdle


def test_theme_pct_exemption_excludes_ticker_from_theme_budget():
    # Fix 4: a `theme_pct` exemption (RULES AM4d's 群創/面板 carve-out) must remove
    # that ticker's effective exposure from its theme's total in the theme-budget
    # check (step 1) — previously only the hard-cap TRIM check (step 2) consulted
    # caps.exemptions at all, so an exempted name still triggered a false-positive
    # theme-budget ALERT.
    holdings = [
        Holding(ticker="EXEMPT", weight=0.25, theme="panel", score=0.5),  # == default hard cap, no TRIM
        Holding(ticker="OTHER", weight=0.05, theme="panel", score=0.5),
    ]
    ips = make_ips()
    ips.caps.exemptions = [CapExemption(ticker="EXEMPT", cap="theme_pct", reason="AM4d subtheme exemption")]

    cards = propose(holdings, [], ips, "us")
    theme_alerts = [c for c in cards if c.action == "ALERT" and c.details.get("theme") == "panel"]
    assert theme_alerts == []  # EXEMPT excluded -> only OTHER's 5% remains, under the 20% cap

    # Sanity: without the exemption, the same holdings DO breach (0.25 + 0.05 = 30% > 20%).
    ips_no_exempt = make_ips()
    cards2 = propose(holdings, [], ips_no_exempt, "us")
    theme_alerts2 = [c for c in cards2 if c.action == "ALERT" and c.details.get("theme") == "panel"]
    assert len(theme_alerts2) == 1
    assert theme_alerts2[0].details["exposure"] == pytest.approx(0.30)

    # Hard-cap TRIM behavior for OTHER exemption types must stay unaffected.
    assert [c for c in cards if c.action == "TRIM"] == []


def test_hard_cap_trim_and_exemption_suppresses_it():
    holdings = [
        Holding(ticker="OVER", weight=0.30, score=0.5),  # over 25% default hard cap
        Holding(ticker="EXEMPT", weight=0.30, score=0.5),
    ]
    ips = make_ips()
    ips.caps.exemptions = [CapExemption(ticker="EXEMPT", cap="position_hard_pct", reason="core position")]

    cards = propose(holdings, [], ips, "us")

    trims = [c for c in cards if c.action == "TRIM"]
    assert [c.sell for c in trims] == ["OVER"]


def test_swap_happy_path_and_hurdle_and_verdict_rejections():
    holdings = [Holding(ticker="WEAK", weight=0.05, score=0.40)]
    ips = make_ips(**{"turnover.hurdle": 0.15, "turnover.verdict_floor": "neutral"})

    challengers = [
        cand("GOOD", final_score=0.60),   # gap 0.20 >= hurdle, verdict ok -> swap
        cand("SMALL_GAP", final_score=0.50),  # gap 0.10 < hurdle -> rejected
    ]
    cards = propose(holdings, challengers, ips, "us", verdicts={"GOOD": "buy", "SMALL_GAP": "buy"})
    swaps = [c for c in cards if c.action == "SWAP"]
    assert len(swaps) == 1
    assert swaps[0].buy == "GOOD" and swaps[0].sell == "WEAK"
    assert swaps[0].score_gap == pytest.approx(0.20)

    # same challenger, but verdict below floor -> rejected despite a big gap.
    cards2 = propose(holdings, [cand("GOOD", final_score=0.60)], ips, "us", verdicts={"GOOD": "underweight"})
    assert [c for c in cards2 if c.action == "SWAP"] == []


def test_hold_rated_challenger_clears_neutral_floor_but_not_overweight():
    # Agents rate on the PortfolioRating scale ("Hold"); the IPS floor is spelled
    # "neutral" — same rung, so a Hold challenger must be judged on its gap.
    holdings = [Holding(ticker="WEAK", weight=0.05, score=0.40)]
    challengers = [cand("HELD", final_score=0.60)]

    ips = make_ips(**{"turnover.hurdle": 0.15, "turnover.verdict_floor": "neutral"})
    cards = propose(holdings, challengers, ips, "us", verdicts={"HELD": "Hold"})
    assert [c.buy for c in cards if c.action == "SWAP"] == ["HELD"]

    ips_high = make_ips(**{"turnover.hurdle": 0.15, "turnover.verdict_floor": "overweight"})
    cards2 = propose(holdings, challengers, ips_high, "us", verdicts={"HELD": "Hold"})
    assert [c for c in cards2 if c.action == "SWAP"] == []


def test_unscored_incumbents_yield_research_alert_and_no_swap():
    holdings = [Holding(ticker="A", weight=0.05, score=None), Holding(ticker="B", weight=0.05, score=None)]
    ips = make_ips()
    challengers = [cand("NEW", final_score=0.99)]

    cards = propose(holdings, challengers, ips, "us", verdicts={"NEW": "buy"})

    assert [c.action for c in cards] == ["ALERT"]
    assert "research" in cards[0].reason.lower() or "screener" in cards[0].reason.lower()


def test_max_swaps_per_week_truncates_with_suppressed_alert():
    holdings = [
        Holding(ticker="W1", weight=0.05, score=0.10),
        Holding(ticker="W2", weight=0.05, score=0.20),
        Holding(ticker="W3", weight=0.05, score=0.30),
    ]
    ips = make_ips(**{"turnover.hurdle": 0.10, "turnover.max_swaps_per_week": 1})
    challengers = [cand("C1", 0.90), cand("C2", 0.80), cand("C3", 0.70)]
    verdicts = {t.ticker: "buy" for t in challengers}

    cards = propose(holdings, challengers, ips, "us", verdicts=verdicts, swaps_this_week=0)

    swaps = [c for c in cards if c.action == "SWAP"]
    assert len(swaps) == 1
    # kept the strongest gap (C1 vs W1: 0.80), suppressed the rest.
    assert swaps[0].buy == "C1"
    suppressed_alerts = [c for c in cards if c.action == "ALERT" and "suppressed" in c.reason.lower()]
    assert len(suppressed_alerts) == 1
    assert suppressed_alerts[0].details["suppressed_count"] == 2
    # the suppressed alert is the very last card.
    assert cards[-1] is suppressed_alerts[0]


def test_incumbent_not_double_swapped():
    holdings = [
        Holding(ticker="W1", weight=0.05, score=0.10),  # weakest
        Holding(ticker="W2", weight=0.05, score=0.20),  # next-weakest
    ]
    ips = make_ips(**{"turnover.hurdle": 0.10, "turnover.max_swaps_per_week": 5})
    challengers = [cand("C1", 0.90), cand("C2", 0.85)]
    verdicts = {"C1": "buy", "C2": "buy"}

    cards = propose(holdings, challengers, ips, "us", verdicts=verdicts)

    swaps = [c for c in cards if c.action == "SWAP"]
    assert len(swaps) == 2
    sells = {c.sell for c in swaps}
    assert sells == {"W1", "W2"}  # each incumbent swapped away at most once
    buys = {c.buy for c in swaps}
    assert buys == {"C1", "C2"}  # each challenger used at most once


def test_friction_gates_a_swap_that_only_clears_the_bare_hurdle():
    # TW round-trip friction is 0.585% -> 0.00585 in score space, so the real
    # threshold is 0.15 + 0.00585 = 0.15585, not the bare 0.15 hurdle.
    holdings = [Holding(ticker="WEAK", weight=0.05, score=0.40)]
    ips = make_ips(**{"turnover.hurdle": 0.15})

    # gap 0.152: over the bare hurdle, under hurdle + friction -> not proposed.
    thin = propose(holdings, [cand("THIN", final_score=0.552)], ips, "tw", verdicts={"THIN": "buy"})
    assert [c for c in thin if c.action == "SWAP"] == []

    # gap 0.16: clears hurdle + friction -> proposed, and the card still cites friction.
    thick = propose(holdings, [cand("THICK", final_score=0.560)], ips, "tw", verdicts={"THICK": "buy"})
    swaps = [c for c in thick if c.action == "SWAP"]
    assert [c.buy for c in swaps] == ["THICK"]
    assert "0.585%" in swaps[0].reason
    assert "friction.tw_roundtrip_pct" in swaps[0].ips_clauses

    # US friction is only 0.02% -> 0.0002, so the same thin gap still clears there.
    us = propose(holdings, [cand("THIN", final_score=0.552)], ips, "us", verdicts={"THIN": "buy"})
    assert [c.buy for c in us if c.action == "SWAP"] == ["THIN"]


def test_us_card_names_hurdle_and_friction_without_a_self_cancelling_total():
    # US friction is 0.02%, so a combined threshold rendered at 3dp reads as the same
    # number as the bare hurdle ("0.150 plus 0.020%, 0.150 together"). The card names
    # the two components instead; score_gap/friction_pct carry the exact figures.
    holdings = [Holding(ticker="TSLA", weight=0.05, score=0.233)]
    ips = make_ips(**{"turnover.hurdle": 0.15})

    cards = propose(holdings, [cand("GE", final_score=0.792)], ips, "us", verdicts={"GE": "neutral"})
    reason = [c for c in cards if c.action == "SWAP"][0].reason
    assert "your IPS turnover hurdle of 0.150 plus estimated round-trip friction of 0.020%." in reason


def test_no_accepted_ips_ever_swaps_below_its_own_hurdle():
    # The invariant the whole friction gate exists for: friction may only ever raise the
    # bar, never lower or erase it. Swept over the values that can reach the gate rather
    # than pinned to one case — the failure modes here were all values no numbered test
    # happened to use (nan erases the comparison, inf suppresses every swap, a negative
    # buys swaps the user's own hurdle rejects).
    #
    # The contract is end-to-end on purpose: for ANY friction value, either validate()
    # rejects the IPS (cli.cmd_propose then refuses to run at all) or propose() honours
    # the hurdle. Neither half alone is worth much — a validate() that rejects everything
    # would pass one, a propose() that proposes nothing would pass the other.
    hostile = (0.0, 0.02, 0.585, 5.0, -10.0, 100.0, float("nan"), float("inf"))
    for hurdle, friction, market, inc, chal in product(
        (0.05, 0.15, 0.40),
        hostile,
        ("us", "tw"),
        (0.0, 0.30, 0.75),
        (0.0, 0.31, 0.76, 1.0),
    ):
        ips = make_ips(**{
            "turnover.hurdle": hurdle,
            "turnover.max_swaps_per_week": 5,
            "friction.tw_roundtrip_pct": friction,
            "friction.us_roundtrip_pct": friction,
        })
        if validate(ips):
            continue  # malformed IPS — the CLI exits 2 before propose() is ever called

        cards = propose(
            [Holding(ticker="INC", weight=0.05, score=inc)],
            [cand("CHA", final_score=chal)],
            ips, market, verdicts={"CHA": "buy"},
        )
        for card in (c for c in cards if c.action == "SWAP"):
            where = f"hurdle={hurdle} friction={friction} market={market} {inc}->{chal}"
            assert card.score_gap >= hurdle, where
            assert card.score_gap >= hurdle + friction / 100, where


# --- T5: thesis-aware monitoring per setup_type -------------------------------
#
# The acceptance fixture: one position per setup_type, all three in the same tape.
# TREND and DIP sit at the same place relative to their MA50 on purpose — the whole
# point of the dispatch is that the same price action means different things.

def thesis_portfolio() -> list[Holding]:
    return [
        Holding(
            ticker="TREND", weight=0.05, score=0.60,
            setup_type="trend_add", entry_price=80.0,
        ),
        Holding(
            ticker="DIP", weight=0.05, score=0.20,
            setup_type="value_dip", entry_price=100.0, invalidation_price=85.0,
        ),
        Holding(
            ticker="ADD", weight=0.05, score=0.30,
            setup_type="pullback_add", entry_price=50.0, invalidation_price=44.0,
        ),
    ]


# every name below its MA50 — a "trend break" for all three, if MA distance were the axis
BELOW_MA = {"TREND": 90.0, "DIP": 90.0, "ADD": 46.0}
MA50 = {"TREND": 100.0, "DIP": 100.0, "ADD": 52.0}


def thesis_alerts(cards) -> dict[str, ProposalCard]:
    return {
        c.details["ticker"]: c
        for c in cards
        if c.action == "ALERT" and "ticker" in c.details
    }


def test_trend_add_alerts_on_ma_break_and_the_dip_setups_do_not():
    """Acceptance clauses 1 and 2: same tape, three positions under their MA50 — only
    the trend_add is alerted, because only its thesis was the trend."""
    cards = propose(
        thesis_portfolio(), [], make_ips(), "us", prices=BELOW_MA, ma50=MA50
    )
    assert set(thesis_alerts(cards)) == {"TREND"}


def test_value_dip_alerts_on_invalidation_breach():
    """Acceptance clause 3: the value_dip's own invalidation price is what ends it —
    and the pullback_add answers to the same rule."""
    breach = {"TREND": 110.0, "DIP": 84.0, "ADD": 43.0}
    cards = propose(
        thesis_portfolio(), [], make_ips(), "us", prices=breach, ma50=MA50
    )
    alerts = thesis_alerts(cards)
    assert set(alerts) == {"DIP", "ADD"}
    assert "85.00" in alerts["DIP"].reason  # cites the level it breached


def test_every_thesis_card_names_its_setup_type_and_entry_price():
    """Acceptance clause 4, plus the spec's "cards must cite the setup_type and
    entry_price" — checked over both trigger paths at once."""
    for prices in (BELOW_MA, {"TREND": 110.0, "DIP": 84.0, "ADD": 43.0}):
        cards = propose(
            thesis_portfolio(), [], make_ips(), "us", prices=prices, ma50=MA50
        )
        alerts = thesis_alerts(cards)
        assert alerts
        for ticker, card in alerts.items():
            holding = next(h for h in thesis_portfolio() if h.ticker == ticker)
            assert holding.setup_type in card.reason
            assert f"{holding.entry_price:.2f}" in card.reason
            assert card.details["setup_type"] == holding.setup_type


def test_a_value_dip_is_never_alerted_on_ma_distance_however_far_it_falls():
    # The spec's "never on MA distance alone", pushed: DIP is 60% under its MA50 and
    # still one cent above its invalidation price.
    holdings = [h for h in thesis_portfolio() if h.ticker == "DIP"]
    cards = propose(
        holdings, [], make_ips(), "us", prices={"DIP": 85.01}, ma50={"DIP": 220.0}
    )
    assert thesis_alerts(cards) == {}


def test_missing_monitoring_fields_are_named_not_silently_unwatched():
    holdings = thesis_portfolio() + [
        Holding(ticker="NODIP", weight=0.05, score=0.5, setup_type="value_dip"),
        Holding(ticker="NOENTRY", weight=0.05, score=0.5, setup_type="trend_add"),
        Holding(ticker="LEGACY", weight=0.05, score=0.5),
        Holding(ticker="OPTOUT", weight=0.05, score=0.5, setup_type="other"),
        Holding(ticker="NOPRICE", weight=0.05, score=0.5, setup_type="trend_add", entry_price=1.0),
    ]
    # NOPRICE is the only one the caller could not price this session. NOENTRY sits
    # *below* its MA50 on purpose: its one watched axis fires, so it is the case where a
    # blanket "nothing is watching this" claim would contradict the run's own alert.
    prices = BELOW_MA | {"NODIP": 10.0, "NOENTRY": 8.0, "LEGACY": 10.0, "OPTOUT": 10.0}
    cards = propose(holdings, [], make_ips(), "us", prices=prices, ma50=MA50 | {"NOENTRY": 9.0})
    gaps = [
        c for c in cards
        if c.action == "ALERT" and (
            c.details.get("unmonitored") or c.details.get("partially_monitored")
        )
    ]
    assert len(gaps) == 1
    named = gaps[0].details["unmonitored"]
    assert set(named) == {"NODIP", "LEGACY", "OPTOUT", "NOPRICE"}
    # NOENTRY is watched on its MA50 — and this run alerted on it, so it is not unwatched
    assert gaps[0].details["partially_monitored"] == ["NOENTRY"]
    assert "NOENTRY" in thesis_alerts(cards)
    for ticker in named + gaps[0].details["partially_monitored"]:
        assert ticker in gaps[0].reason
    # the three fully-equipped positions are watched, so they are not in the gap list
    assert not {"TREND", "DIP", "ADD"} & set(named)


def test_pre_t3_portfolio_is_untouched_by_monitoring():
    # No holding carries a setup_type -> thesis monitoring is not in use, nothing can
    # look monitored, and propose() behaves exactly as it did before T5.
    holdings = [Holding(ticker="OK", weight=0.05, score=0.5)]
    assert propose(holdings, [], make_ips(), "us") == []


def test_monitor_inputs_reads_the_last_session_and_skips_short_history():
    import pandas as pd

    from kuroshio.core.allocator.signals import monitor_inputs

    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=60)]
    close = pd.DataFrame(
        {
            "LONG": [float(i) for i in range(60)],   # 60 sessions -> MA50 exists
            "SHORT": [float("nan")] * 20 + [100.0] * 40,  # only 40 -> no MA50
        },
        index=dates,
    )
    prices, ma50, asof = monitor_inputs(Panel(close=close, volume=close))

    assert asof == dates[-1]
    assert prices == {"LONG": 59.0, "SHORT": 100.0}
    # mean of 10..59
    assert ma50 == {"LONG": pytest.approx(34.5)}


# --- PR #9 round 1 repairs -----------------------------------------------------


def test_a_partially_monitored_position_is_not_also_claimed_unwatched():
    """R1: NOENTRY has no entry_price but its MA50 break *is* watched — and here it
    breaks, so the same run alerts on it. The coverage card must not also claim the run
    says nothing about it either way; that claim belongs to LEGACY alone."""
    holdings = [
        Holding(ticker="NOENTRY", weight=0.05, score=0.5, setup_type="trend_add"),
        Holding(ticker="LEGACY", weight=0.05, score=0.5),
    ]
    cards = propose(
        holdings, [], make_ips(), "us",
        prices={"NOENTRY": 90.0, "LEGACY": 10.0}, ma50={"NOENTRY": 100.0},
    )
    assert "NOENTRY" in thesis_alerts(cards)  # the trend break is alerted
    gap = next(
        c for c in cards
        if c.details.get("unmonitored") or c.details.get("partially_monitored")
    )
    assert gap.details["unmonitored"] == ["LEGACY"]
    assert gap.details["partially_monitored"] == ["NOENTRY"]
    # and the two claims are per-item, not one blanket sentence over both
    blanket, partly = gap.reason.split("Partly watched:")
    assert "NOENTRY" not in blanket
    assert "LEGACY" not in partly


def test_ma50_survives_a_suspension_gap_inside_the_window():
    """R3: one missing session (a FinMind suspension day, or a non-reference ticker on
    yf's reference calendar) must not void MA50 for a ticker with 199 real sessions."""
    import pandas as pd

    from kuroshio.core.allocator.signals import monitor_inputs

    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=200)]
    holed = [100.0] * 200
    holed[190] = float("nan")  # suspended, inside the trailing 50
    close = pd.DataFrame({"CLEAN": [100.0] * 200, "HOLE": holed}, index=dates)
    prices, ma50, asof = monitor_inputs(Panel(close=close, volume=close))

    assert asof == dates[-1]
    assert prices == {"CLEAN": 100.0, "HOLE": 100.0}
    assert ma50 == {"CLEAN": 100.0, "HOLE": 100.0}

    # end to end: the trend_add stays monitored, and is not told it has too little history
    holdings = [Holding(
        ticker="HOLE", weight=0.05, score=0.5, setup_type="trend_add", entry_price=90.0
    )]
    cards = propose(holdings, [], make_ips(), "us", prices=prices, ma50=ma50)
    assert cards == []


def test_swap_selling_a_monitored_incumbent_says_whether_its_thesis_is_intact():
    """R5: the SWAP card's sell side is a value_dip monitoring just checked and left
    alone. The card must name the setup_type and the state, so the two halves of the
    run visibly agree instead of both going silent."""
    holdings = [h for h in thesis_portfolio() if h.ticker in ("TREND", "DIP")]
    cards = propose(
        holdings, [cand("NEW", 0.95)], make_ips(), "us", verdicts={"NEW": "buy"},
        prices={"TREND": 110.0, "DIP": 90.0}, ma50=MA50,
    )
    assert thesis_alerts(cards) == {}  # both theses intact this run
    swap = next(c for c in cards if c.action == "SWAP")
    assert swap.sell == "DIP"
    assert "value_dip" in swap.reason
    assert "85.00" in swap.reason  # the invalidation level monitoring checked
    assert "not breached" in swap.reason
    assert swap.details["incumbent_setup_type"] == "value_dip"


def test_swap_selling_an_intact_trend_add_says_the_trend_is_intact():
    """R10: the trend_add-intact branch of the same bridge. Unpinned, it could be
    flipped to say the trend has broken while no ALERT says any such thing."""
    holdings = [h for h in thesis_portfolio() if h.ticker == "TREND"]
    cards = propose(
        holdings, [cand("NEW", 0.95)], make_ips(), "us", verdicts={"NEW": "buy"},
        prices={"TREND": 110.0}, ma50=MA50,
    )
    assert thesis_alerts(cards) == {}
    swap = next(c for c in cards if c.action == "SWAP")
    assert swap.sell == "TREND"
    assert "its trend is intact" in swap.reason
    assert "at or above its 50-day moving average of 100.00" in swap.reason
    assert "broken" not in swap.reason


def test_swap_selling_an_incumbent_whose_thesis_broke_agrees_with_the_alert():
    """R10: the third branch. This is the R1 defect one card over — an ALERT saying the
    thesis broke and a SWAP below it calling the same position intact — so the SWAP's
    wording is pinned against the ALERT that ran in the same call."""
    holdings = [h for h in thesis_portfolio() if h.ticker in ("TREND", "DIP")]
    cards = propose(
        holdings, [cand("NEW", 0.95)], make_ips(), "us", verdicts={"NEW": "buy"},
        prices={"TREND": 110.0, "DIP": 84.0}, ma50=MA50,
    )
    assert set(thesis_alerts(cards)) == {"DIP"}
    swap = next(c for c in cards if c.action == "SWAP")
    assert swap.sell == "DIP"
    assert "its thesis broke this run — see the ALERT above" in swap.reason
    assert "intact" not in swap.reason


@pytest.mark.parametrize("days_from_today", [-400, -1, 0, 1])
def test_the_card_names_the_session_and_claims_nothing_about_its_state(days_from_today):
    """R6/R9: nothing in the run knows whether the session it read is open or closed —
    that needs the market's close time in the market's own timezone, and the local
    machine clock is not it (Taipei 01:00 with --market us is mid-NYSE-session on
    *yesterday's* label; Taipei 21:00 with --market tw is hours past the close on
    today's). So the card names the label and stops. asof is varied against the local
    date because a comparison between the two was exactly the bug."""
    asof = (datetime.date.today() + datetime.timedelta(days=days_from_today)).isoformat()
    holdings = [h for h in thesis_portfolio() if h.ticker == "DIP"]
    cards = propose(
        holdings, [], make_ips(), "us", prices={"DIP": 84.0}, ma50=MA50, asof=asof
    )
    card = thesis_alerts(cards)["DIP"]
    assert f"at 84.00 ({asof} session)" in card.reason
    assert "closed at" not in card.reason
    assert "still-open" not in card.reason
    assert card.details["asof"] == asof


# --- T6: forced decision card at max adverse excursion -------------------------
#
# The rule dispatches on nothing: any position with an entry price can be far enough
# underwater to force a decision, whatever setup opened it.


def decides(cards) -> list[ProposalCard]:
    return [c for c in cards if c.action == "DECIDE"]


def loser(price: float, entry: float = 100.0, **kw) -> tuple[list[Holding], dict[str, float]]:
    kw.setdefault("score", 0.5)
    return [Holding(ticker="LOSER", weight=0.05, entry_price=entry, **kw)], {"LOSER": price}


def test_a_position_past_the_mae_threshold_gets_exactly_one_decide_card():
    """Acceptance clause 1: below the threshold -> exactly one DECIDE card citing the
    IPS clause. Its whole text is pinned, not a substring: the card's job is to refuse
    the fourth option, so any re-wording that softens that must go red."""
    holdings, prices = loser(80.0)  # -20% from entry, past the default -15%
    cards = propose(holdings, [], make_ips(), "us", prices=prices, asof="2026-08-27")

    assert len(decides(cards)) == 1
    card = decides(cards)[0]
    assert card.ips_clauses == ["caps.max_adverse_excursion_pct"]
    assert card.details == {
        "ticker": "LOSER", "entry_price": 100.0, "price": 80.0, "asof": "2026-08-27",
        "drawdown": pytest.approx(-0.20), "threshold_pct": -15, "trigger_price": 85.0,
    }
    assert card.reason == (
        "LOSER is -20.0% from your entry price of 100.00, at 80.00 (2026-08-27 session) "
        "— at or past your IPS max adverse excursion of -15.0%, the 85.00 level from that "
        "entry. Decide: kill it, add to it per the plan you opened it with, or rewrite the "
        "thesis and record the new one. Holding it unchanged is not one of the three."
    )
    assert card.to_markdown().splitlines()[0] == "### DECIDE LOSER"


def test_a_position_above_the_mae_threshold_gets_no_decide_card():
    """Acceptance clause 2 — and a winner is not a loser: both sides of zero."""
    for price in (86.0, 100.0, 140.0):
        holdings, prices = loser(price)
        assert decides(propose(holdings, [], make_ips(), "us", prices=prices)) == []


def test_the_mae_threshold_is_read_from_the_ips():
    """Acceptance clause 3: the same position at the same price decides or does not,
    purely on the IPS number."""
    holdings, prices = loser(80.0)
    wide = make_ips(**{"caps.max_adverse_excursion_pct": -30})
    tight = make_ips(**{"caps.max_adverse_excursion_pct": -5})

    assert decides(propose(holdings, [], wide, "us", prices=prices)) == []
    # no asof: the card names the price and no session (T49's branch, on this card)
    assert "of 100.00, at 80.00 — at or past" in decides(
        propose(holdings, [], make_ips(), "us", prices=prices)
    )[0].reason
    tight_card = decides(propose(holdings, [], tight, "us", prices=prices))
    assert len(tight_card) == 1
    assert "-5.0%, the 95.00 level" in tight_card[0].reason


def test_a_position_exactly_at_the_mae_threshold_decides():
    """The boundary, pinned: the threshold is a level the position may not close past,
    so touching it is past it. The comparison is against the trigger price the card
    prints (entry x (1 + pct/100)), never a re-derived ratio — see T15 for what the
    round trip through a ratio does to an exact boundary."""
    holdings, prices = loser(85.0)  # exactly -15% of a 100.00 entry
    assert len(decides(propose(holdings, [], make_ips(), "us", prices=prices))) == 1
    holdings, prices = loser(85.01)
    assert decides(propose(holdings, [], make_ips(), "us", prices=prices)) == []


def test_the_mae_rule_reads_no_setup_type():
    """A loss is a loss: the same drawdown decides under every setup_type and under
    none. The trend_add case is T41's shape — deep underwater, still above its MA50,
    silent until this card."""
    for setup in ("value_dip", "pullback_add", "trend_add", "other", None):
        holdings, prices = loser(60.0, setup_type=setup, invalidation_price=1.0)
        cards = propose(
            holdings, [], make_ips(), "us", prices=prices, ma50={"LOSER": 50.0}
        )
        assert len(decides(cards)) == 1, setup
        assert thesis_alerts(cards) == {}, setup  # no thesis rule fired: this is the MAE card alone


def test_positions_the_mae_rule_cannot_judge_are_named_not_dropped():
    """No entry_price, a non-positive one, or no price this session — none of the three
    can be judged, so none of the three gets a DECIDE, and all three are named on the
    same coverage card T5 already emits rather than on a second one."""
    holdings = [
        Holding(ticker="WATCHED", weight=0.05, score=0.5, entry_price=100.0),
        Holding(ticker="NOENTRY", weight=0.05, score=0.5),
        Holding(ticker="ZEROENTRY", weight=0.05, score=0.5, entry_price=0.0),
        # a trend_add so that *both* rules are stopped by the one missing price
        Holding(ticker="NOPRICE", weight=0.05, score=0.5, entry_price=100.0, setup_type="trend_add"),
    ]
    prices = {"WATCHED": 50.0, "NOENTRY": 50.0, "ZEROENTRY": 50.0}
    cards = propose(holdings, [], make_ips(), "us", prices=prices)

    assert [c.details["ticker"] for c in decides(cards)] == ["WATCHED"]
    gaps = [c for c in cards if c.details.get("unmonitored")]
    assert len(gaps) == 1
    assert set(gaps[0].details["unmonitored"]) == {"NOENTRY", "ZEROENTRY", "NOPRICE"}
    assert gaps[0].details["partially_monitored"] == ["WATCHED"]  # judged on its loss only
    assert (
        "NOENTRY (no setup_type; no entry_price, so the loss from entry is not watched)"
        in gaps[0].reason
    )
    # 0.0 is not "unrecorded": the card says what it found rather than what it wishes for
    assert "ZEROENTRY (no setup_type; entry_price 0.0 is not a price," in gaps[0].reason
    # both rules read the session price, and a position without one states that once
    assert "NOPRICE (no price for this session)" in gaps[0].reason

    # one gate, both rules: a 0.0 entry reads as "not recorded" on the thesis card too,
    # and reaches details as None rather than as a price the run divided by (T43).
    zero = propose(
        [Holding(ticker="Z", weight=0.05, score=0.5, setup_type="trend_add", entry_price=0.0)],
        [], make_ips(), "us", prices={"Z": 90.0}, ma50={"Z": 100.0},
    )
    assert "entry price not recorded" in thesis_alerts(zero)["Z"].reason
    assert thesis_alerts(zero)["Z"].details["entry_price"] is None


def test_a_position_watched_only_by_the_mae_rule_is_not_called_unwatched():
    """The contradiction guard. Before T6 nothing watched a `setup_type: other`, and the
    coverage card said so. It is watched now, so it moves to the partly-watched group —
    one run must not claim both that a position is unwatched and that it must be decided
    on today."""
    holdings = [
        Holding(ticker="OPTOUT", weight=0.05, score=0.5, setup_type="other", entry_price=100.0),
        Holding(ticker="LEGACY", weight=0.05, score=0.5),
    ]
    cards = propose(holdings, [], make_ips(), "us", prices={"OPTOUT": 50.0, "LEGACY": 50.0})

    assert [c.details["ticker"] for c in decides(cards)] == ["OPTOUT"]
    gap = next(c for c in cards if c.details.get("unmonitored") or c.details.get("partially_monitored"))
    assert gap.details["unmonitored"] == ["LEGACY"]
    assert gap.details["partially_monitored"] == ["OPTOUT"]
    assert gap.reason.startswith("2 position(s) are not fully monitored.")  # both groups counted
    blanket, partly = gap.reason.split("Partly watched")
    assert "OPTOUT" not in blanket

    # and with nothing unwatched, the card is the partly-watched sentence alone
    only_partial = next(
        c for c in propose(holdings[:1], [], make_ips(), "us", prices={"OPTOUT": 50.0})
        if c.details.get("partially_monitored")
    )
    assert only_partial.reason == (
        "1 position(s) are not fully monitored. Partly watched: one of the two rules ran "
        "on each of these this session and the other could not — OPTOUT (setup_type 'other')."
    )


def test_the_decide_card_quotes_what_thesis_monitoring_concluded():
    """A position can be past the threshold and in breach of its invalidation price at
    once. Both cards ship — they answer different questions — so the DECIDE quotes step
    3's conclusion instead of the two cards talking past each other about one ticker."""
    breached = [h for h in thesis_portfolio() if h.ticker == "DIP"]  # entry 100, invalidation 85
    cards = propose(breached, [], make_ips(), "us", prices={"DIP": 84.0}, ma50=MA50)
    assert set(thesis_alerts(cards)) == {"DIP"}
    card = decides(cards)[0]
    assert card.reason.endswith(
        " Monitoring checked DIP this run: it is a value_dip and its thesis broke this "
        "run — see the ALERT above."
    )
    assert cards.index(thesis_alerts(cards)["DIP"]) < cards.index(card)  # "above" is true

    intact = [Holding(
        ticker="DIP", weight=0.05, score=0.2, setup_type="value_dip",
        entry_price=100.0, invalidation_price=70.0,
    )]
    cards = propose(intact, [], make_ips(), "us", prices={"DIP": 84.0}, ma50=MA50)
    assert thesis_alerts(cards) == {}
    assert decides(cards)[0].reason.endswith(
        " Monitoring checked DIP this run: it is a value_dip and its invalidation price "
        "of 70.00 is not breached — at 84.00."
    )


def test_a_pre_t3_portfolio_still_gets_no_cards_at_all():
    """No entry_price anywhere -> the MAE rule is not in use either, so the coverage
    card stays off exactly as it did before T6."""
    holdings = [Holding(ticker="OK", weight=0.05, score=0.5)]
    assert propose(holdings, [], make_ips(), "us", prices={"OK": 10.0}) == []
