import pytest

from kuroshio.core.allocator import propose
from kuroshio.core.ips import IPS
from kuroshio.core.ips.schema import CapExemption
from kuroshio.types import Candidate, Holding


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
