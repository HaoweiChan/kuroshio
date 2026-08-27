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
    # NOPRICE is the only one the caller could not price this session
    prices = BELOW_MA | {"NODIP": 10.0, "NOENTRY": 10.0, "LEGACY": 10.0, "OPTOUT": 10.0}
    cards = propose(holdings, [], make_ips(), "us", prices=prices, ma50=MA50 | {"NOENTRY": 9.0})
    gaps = [c for c in cards if c.action == "ALERT" and c.details.get("unmonitored")]
    assert len(gaps) == 1
    named = gaps[0].details["unmonitored"]
    assert set(named) == {"NODIP", "NOENTRY", "LEGACY", "OPTOUT", "NOPRICE"}
    for ticker in named:
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
    prices, ma50 = monitor_inputs(Panel(close=close, volume=close))

    assert prices == {"LONG": 59.0, "SHORT": 100.0}
    # mean of 10..59
    assert ma50 == {"LONG": pytest.approx(34.5)}
