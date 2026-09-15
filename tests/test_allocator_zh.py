"""TASK-22: propose() cards render in the IPS lang (zh = Traditional Chinese).

One test per `action=` site in `core/allocator/engine.py`, plus every conditional
clause of its reason, run with `lang="zh"` — each asserts the reason carries no run
of three lowercase English words, and that the `### ` head, tickers, numbers and IPS
clause keys are unchanged from the English card for the same inputs. Separately:
lang resolution (None -> ips.lang, en/unknown -> English byte-for-byte, zh/zh-TW/
zh_TW -> Chinese) and `ProposalCard.to_markdown()`'s detail-line labels.
"""

from __future__ import annotations

import re

import pytest

from kuroshio.core.allocator import propose
from kuroshio.core.ips import IPS
from kuroshio.types import Candidate, Holding, ProposalCard

# a run of three lowercase english words separated by single spaces — the probe's own
# regex (task-22's Probe: line), reused here so the unit tests catch what it would.
_ENGLISH_RUN = re.compile(r"[a-z]{2,} [a-z]{2,} [a-z]{2,}")


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


def assert_zh(card: ProposalCard, *, must_contain: list[str] = ()):
    assert _ENGLISH_RUN.search(card.reason) is None, card.reason
    for s in must_contain:
        assert s in card.reason, card.reason


def assert_same_shape(en: ProposalCard, zh: ProposalCard):
    """The head, tickers-via-sell/buy/details, ips_clauses and every number-bearing
    detail are unchanged by translation."""
    assert en.action == zh.action
    assert en.to_markdown().splitlines()[0] == zh.to_markdown().splitlines()[0]
    assert en.sell == zh.sell
    assert en.buy == zh.buy
    assert en.ips_clauses == zh.ips_clauses
    assert en.score_gap == zh.score_gap
    assert en.friction_pct == zh.friction_pct


def rating_row(rating: str, **kw) -> dict:
    row = {
        "date": "2026-08-20", "market": "us", "ticker": "T", "rating": rating,
        "stop_loss": 42.0, "price_target": 55.0, "close": None,
        "source": "claude-session", "model": "claude-opus-4",
    }
    row.update(kw)
    return row


# --- 1. theme budget ALERT --------------------------------------------------------


def test_theme_budget_alert_zh():
    holdings = [
        Holding(ticker="AAA", weight=0.15, theme="ai", score=0.85),
        Holding(ticker="BBB", weight=0.15, theme="ai", score=0.90),
    ]
    en = next(c for c in propose(holdings, [], make_ips(), "us") if c.action == "ALERT")
    zh = next(c for c in propose(holdings, [], make_ips(), "us", lang="zh") if c.action == "ALERT")
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["ai", "30.0%", "20.0%"])


# --- 2. hard-cap TRIM, all three target_weight variants ---------------------------


def test_hard_cap_trim_zh_base_cap_no_stop():
    holdings = [Holding(ticker="OVER", weight=0.30, score=0.5)]
    ips = make_ips(**{"caps.position_pct": 8})
    en = next(c for c in propose(holdings, [], ips, "us") if c.action == "TRIM")
    zh = next(c for c in propose(holdings, [], ips, "us", lang="zh") if c.action == "TRIM")
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["OVER", "8.0%", "30.0%"])


def test_hard_cap_trim_zh_risk_cap_binds():
    holdings = [
        Holding(ticker="OVER", weight=0.30, score=0.5, entry_price=100.0, invalidation_price=90.0)
    ]
    ips = make_ips(**{"caps.position_pct": 10, "caps.risk_budget_pct": 0.5})
    en = next(c for c in propose(holdings, [], ips, "us") if c.action == "TRIM")
    zh = next(c for c in propose(holdings, [], ips, "us", lang="zh") if c.action == "TRIM")
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["5.0%", "caps.risk_budget_pct" in zh.ips_clauses and "100.00"])


def test_hard_cap_trim_zh_base_cap_tighter_than_risk():
    holdings = [
        Holding(ticker="OVER", weight=0.30, score=0.5, entry_price=100.0, invalidation_price=110.0)
    ]
    ips = make_ips(**{"caps.position_pct": 10, "caps.risk_budget_pct": 0.5})
    en = next(c for c in propose(holdings, [], ips, "us") if c.action == "TRIM")
    zh = next(c for c in propose(holdings, [], ips, "us", lang="zh") if c.action == "TRIM")
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["10.0%"])


# --- 3. book vol SCALE -------------------------------------------------------------


def test_book_vol_scale_zh():
    holdings = [Holding(ticker="A", weight=0.5, score=0.5)]
    ips = make_ips(**{"caps.book_vol_target_pct": 15})
    en = next(
        c for c in propose(holdings, [], ips, "us", book_vol=30.0) if c.action == "SCALE"
    )
    zh = next(
        c for c in propose(holdings, [], ips, "us", book_vol=30.0, lang="zh")
        if c.action == "SCALE"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["30.0%", "15.0%", "50%"])


# --- 4. stop ratchet ALERT, both was_clause variants -------------------------------


def test_ratchet_alert_zh_no_prior_stop():
    holdings = [
        Holding(
            ticker="T", weight=0.05, score=0.5, entry_date="2026-01-05",
            setup_type="trend_add", entry_price=100.0,
        )
    ]
    kw = dict(prices={"T": 140.0}, ma50={"T": 120.0}, running_high={"T": 150.0}, atr14={"T": 5.0})
    en = next(c for c in propose(holdings, [], make_ips(), "us", **kw) if c.details.get("ratchet"))
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.details.get("ratchet")
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["T", "135.00", "150.00", "2026-01-05"])


def test_ratchet_alert_zh_prior_stop_known():
    holdings = [
        Holding(
            ticker="T", weight=0.05, score=0.5, entry_date="2026-01-05",
            setup_type="trend_add", entry_price=100.0, invalidation_price=120.0,
        )
    ]
    # 150 - 3*5 = 135 < 120 recorded, so widen the ATR so the trail clears 120.
    kw = dict(prices={"T": 200.0}, ma50={"T": 120.0}, running_high={"T": 200.0}, atr14={"T": 20.0})
    en = next(c for c in propose(holdings, [], make_ips(), "us", **kw) if c.details.get("ratchet"))
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.details.get("ratchet")
    )
    assert_same_shape(en, zh)
    assert "120.00" in zh.reason


# --- 5/6/7. thesis monitoring ALERTs (trend MA break, trend trail breach x3 levels,
#            value_dip/pullback_add invalidation breach) -----------------------------


def thesis_portfolio() -> list[Holding]:
    return [
        Holding(ticker="TREND", weight=0.05, score=0.60, setup_type="trend_add", entry_price=80.0),
        Holding(
            ticker="DIP", weight=0.05, score=0.20, setup_type="value_dip",
            entry_price=100.0, invalidation_price=85.0,
        ),
        Holding(
            ticker="ADD", weight=0.05, score=0.30, setup_type="pullback_add",
            entry_price=50.0, invalidation_price=44.0,
        ),
    ]


BELOW_MA = {"TREND": 90.0, "DIP": 90.0, "ADD": 46.0}
MA50 = {"TREND": 100.0, "DIP": 100.0, "ADD": 52.0}


def thesis_alerts(cards):
    return {c.details["ticker"]: c for c in cards if c.action == "ALERT" and "ticker" in c.details}


def test_trend_add_ma_break_alert_zh():
    en = thesis_alerts(propose(thesis_portfolio(), [], make_ips(), "us", prices=BELOW_MA, ma50=MA50))
    zh = thesis_alerts(
        propose(thesis_portfolio(), [], make_ips(), "us", prices=BELOW_MA, ma50=MA50, lang="zh")
    )
    assert_same_shape(en["TREND"], zh["TREND"])
    assert_zh(zh["TREND"], must_contain=["TREND", "80.00", "100.00"])


def test_value_dip_and_pullback_invalidation_breach_alert_zh():
    breach = {"TREND": 110.0, "DIP": 84.0, "ADD": 43.0}
    en = thesis_alerts(propose(thesis_portfolio(), [], make_ips(), "us", prices=breach, ma50=MA50))
    zh = thesis_alerts(
        propose(thesis_portfolio(), [], make_ips(), "us", prices=breach, ma50=MA50, lang="zh")
    )
    for ticker in ("DIP", "ADD"):
        assert_same_shape(en[ticker], zh[ticker])
        assert_zh(zh[ticker], must_contain=[ticker])
    assert "85.00" in zh["DIP"].reason


def test_trend_add_trailing_stop_breach_alert_zh_level_variants():
    # level variant a: the ratchet moved it *this* run (moved.add fires first).
    holdings = [
        Holding(
            ticker="T", weight=0.05, score=0.5, entry_date="2026-01-05",
            setup_type="trend_add", entry_price=100.0,
        )
    ]
    kw = dict(prices={"T": 130.0}, ma50={"T": 120.0}, running_high={"T": 150.0}, atr14={"T": 5.0})
    en = [c for c in propose(holdings, [], make_ips(), "us", **kw) if c.details.get("ticker") == "T"]
    zh = [
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.details.get("ticker") == "T"
    ]
    breach_en = next(c for c in en if not c.details.get("ratchet"))
    breach_zh = next(c for c in zh if not c.details.get("ratchet"))
    assert_same_shape(breach_en, breach_zh)
    assert_zh(breach_zh, must_contain=["T", "135.00"])

    # level variant c: the recorded invalidation_price, never ratcheted (trail is lower).
    holdings2 = [
        Holding(
            ticker="T", weight=0.05, score=0.5, entry_date="2026-01-05",
            setup_type="trend_add", entry_price=100.0, invalidation_price=140.0,
        )
    ]
    kw2 = dict(prices={"T": 139.0}, ma50={"T": 120.0}, running_high={"T": 150.0}, atr14={"T": 5.0})
    en2 = next(
        c for c in propose(holdings2, [], make_ips(), "us", **kw2) if c.details.get("ticker") == "T"
    )
    zh2 = next(
        c for c in propose(holdings2, [], make_ips(), "us", lang="zh", **kw2)
        if c.details.get("ticker") == "T"
    )
    assert_same_shape(en2, zh2)
    assert_zh(zh2, must_contain=["140.00"])


# --- 9. DECIDE (max adverse excursion), both lead variants + monitor-note ----------


def loser(price: float, entry: float = 100.0, **kw):
    kw.setdefault("score", 0.5)
    return [Holding(ticker="LOSER", weight=0.05, entry_price=entry, **kw)], {"LOSER": price}


def test_mae_decide_zh_current_price_lead():
    holdings, prices = loser(80.0)
    en = next(c for c in propose(holdings, [], make_ips(), "us", prices=prices) if c.action == "DECIDE")
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", prices=prices, lang="zh")
        if c.action == "DECIDE"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["LOSER", "-20.0%", "100.00", "80.00", "-15.0%"])


def test_mae_decide_zh_recovered_lead_and_monitor_note():
    # a low since entry worse than this session's price -> the "fell to ... and is back
    # ... " lead; plus a monitored setup_type so the trailing monitor-note is appended.
    holdings = [
        Holding(
            ticker="LOSER", weight=0.05, score=0.5, entry_price=100.0, entry_date="2026-01-01",
            setup_type="value_dip", invalidation_price=1.0,
        )
    ]
    kw = dict(prices={"LOSER": 90.0}, min_close={"LOSER": 60.0})
    en = next(c for c in propose(holdings, [], make_ips(), "us", **kw) if c.action == "DECIDE")
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.action == "DECIDE"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["LOSER", "60.00", "2026-01-01", "value_dip"])
    assert "Monitoring checked" not in zh.reason


# --- 10. missing-price ALERT --------------------------------------------------------


def test_missing_price_alert_zh():
    holdings = [
        Holding(ticker="OK", weight=0.05, score=0.5, entry_price=10.0),
        Holding(ticker="GONE", weight=0.05, score=0.5, entry_price=10.0),
    ]
    prices = {"OK": 11.0}
    en = next(
        c for c in propose(holdings, [], make_ips(), "us", prices=prices)
        if c.details.get("missing") is not None
    )
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", prices=prices, lang="zh")
        if c.details.get("missing") is not None
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["GONE", "1", "2"])


# --- 11. coverage ALERT: unmonitored-only, partial-only, and both ------------------


def test_coverage_alert_zh_unmonitored_and_partial():
    holdings = [
        Holding(ticker="NOENTRY", weight=0.05, score=0.5, setup_type="trend_add"),
        Holding(ticker="LEGACY", weight=0.05, score=0.5),
    ]
    kw = dict(prices={"NOENTRY": 90.0, "LEGACY": 10.0}, ma50={"NOENTRY": 100.0})
    en = next(
        c for c in propose(holdings, [], make_ips(), "us", **kw)
        if c.details.get("unmonitored") or c.details.get("partially_monitored")
    )
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.details.get("unmonitored") or c.details.get("partially_monitored")
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["LEGACY", "NOENTRY", "2"])


def test_coverage_alert_zh_partial_only():
    holdings = [
        Holding(ticker="OPTOUT", weight=0.05, score=0.5, setup_type="other", entry_price=100.0),
    ]
    kw = dict(prices={"OPTOUT": 50.0})
    en = next(
        c for c in propose(holdings, [], make_ips(), "us", **kw)
        if c.details.get("partially_monitored")
    )
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw)
        if c.details.get("partially_monitored")
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["OPTOUT", "1"])


# --- 12. rating veto DECIDE: plain, folded with MAE, and "not recorded" stop -------


def test_rating_veto_decide_zh():
    holdings = [Holding(ticker="T", weight=0.05, score=0.5)]
    en = next(
        c for c in propose(holdings, [], make_ips(), "us", ratings_held={"T": rating_row("Sell")})
        if c.action == "DECIDE"
    )
    zh = next(
        c for c in propose(
            holdings, [], make_ips(), "us", lang="zh", ratings_held={"T": rating_row("Sell")}
        )
        if c.action == "DECIDE"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["T", "Sell", "2026-08-20", "claude-session", "claude-opus-4", "42.00"])


def test_rating_veto_decide_zh_no_stop_recorded():
    holdings = [Holding(ticker="T", weight=0.05, score=0.5)]
    row = rating_row("Sell", stop_loss=None)
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", ratings_held={"T": row})
        if c.action == "DECIDE"
    )
    assert_zh(zh)
    assert "not recorded" not in zh.reason


def test_mae_and_rating_veto_fold_into_one_decide_card_zh():
    holdings = [Holding(ticker="LOSER", weight=0.05, score=0.2, entry_price=100.0)]
    kw = dict(prices={"LOSER": 80.0}, ratings_held={"LOSER": rating_row("Sell")})
    en = next(c for c in propose(holdings, [], make_ips(), "us", **kw) if c.action == "DECIDE")
    zh = next(
        c for c in propose(holdings, [], make_ips(), "us", lang="zh", **kw) if c.action == "DECIDE"
    )
    assert_same_shape(en, zh)
    assert zh.details["kind"] == "mae+rating"
    assert_zh(zh, must_contain=["LOSER", "-20.0%", "Sell"])


# --- 13. no-score ALERT -------------------------------------------------------------


def test_no_score_alert_zh():
    holdings = [Holding(ticker="A", weight=0.05)]
    en = next(c for c in propose(holdings, [], make_ips(), "us") if c.action == "ALERT")
    zh = next(c for c in propose(holdings, [], make_ips(), "us", lang="zh") if c.action == "ALERT")
    assert_same_shape(en, zh)
    assert_zh(zh)


# --- 14. SWAP: main, sizing, bridge, decided-addendum, both disclosure variants ----


def test_swap_card_zh_plain():
    holdings = [Holding(ticker="AAA", weight=0.15, score=0.85)]
    en = next(
        c for c in propose(holdings, [cand("XXX", 0.95)], make_ips(**{"turnover.hurdle": 0.05}), "us")
        if c.action == "SWAP"
    )
    zh = next(
        c for c in propose(
            holdings, [cand("XXX", 0.95)], make_ips(**{"turnover.hurdle": 0.05}), "us", lang="zh"
        )
        if c.action == "SWAP"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["XXX", "AAA", "0.950", "0.850", "neutral"])


def test_swap_card_zh_bridge_and_decided_addendum():
    holdings = [
        Holding(ticker="LOSER", weight=0.05, theme="t", score=0.2, entry_price=100.0),
        Holding(ticker="OK", weight=0.05, score=0.9),
    ]
    kw = dict(verdicts={"NEW": "buy"}, themes={"NEW": "t"}, prices={"LOSER": 70.0})
    en = next(
        c for c in propose(holdings, [cand("NEW", 0.9)], make_ips(), "us", **kw)
        if c.action == "SWAP"
    )
    zh = next(
        c for c in propose(holdings, [cand("NEW", 0.9)], make_ips(), "us", lang="zh", **kw)
        if c.action == "SWAP"
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["LOSER", "-30.0%", "NEW"])


def test_swap_card_zh_disclosure_both_and_one_auto_filled():
    holdings = [Holding(ticker="AAA", weight=0.15, score=0.5)]
    ips = make_ips(**{"turnover.hurdle": 0.05})

    both_kw = dict(auto_scored={"AAA": 40, "XXX": 40}, pool_source=None)
    en_both = next(
        c for c in propose(holdings, [cand("XXX", 0.9)], ips, "us", **both_kw) if c.action == "SWAP"
    )
    zh_both = next(
        c for c in propose(holdings, [cand("XXX", 0.9)], ips, "us", lang="zh", **both_kw)
        if c.action == "SWAP"
    )
    assert_same_shape(en_both, zh_both)
    assert_zh(zh_both, must_contain=["AAA", "XXX", "40"])
    assert "your own files" not in zh_both.reason

    one_kw = dict(auto_scored={"XXX": 40}, pool_source="universe.txt")
    en_one = next(
        c for c in propose(holdings, [cand("XXX", 0.9)], ips, "us", **one_kw) if c.action == "SWAP"
    )
    zh_one = next(
        c for c in propose(holdings, [cand("XXX", 0.9)], ips, "us", lang="zh", **one_kw)
        if c.action == "SWAP"
    )
    assert_same_shape(en_one, zh_one)
    assert_zh(zh_one, must_contain=["XXX", "AAA", "universe.txt"])
    assert "the universe in" not in zh_one.reason


# --- 15. suppressed swaps ALERT -----------------------------------------------------


def test_suppressed_swaps_alert_zh():
    holdings = [
        Holding(ticker="A", weight=0.05, score=0.1),
        Holding(ticker="B", weight=0.05, score=0.2),
    ]
    ips = make_ips(**{"turnover.hurdle": 0.05, "turnover.max_swaps_per_week": 1})
    challengers = [cand("X", 0.9), cand("Y", 0.8)]
    en = next(
        c for c in propose(holdings, challengers, ips, "us", swaps_this_week=0)
        if c.details.get("suppressed_count") is not None
    )
    zh = next(
        c for c in propose(holdings, challengers, ips, "us", swaps_this_week=0, lang="zh")
        if c.details.get("suppressed_count") is not None
    )
    assert_same_shape(en, zh)
    assert_zh(zh, must_contain=["1"])


# --- AC #2: lang resolution ----------------------------------------------------------


def test_lang_none_uses_ips_lang():
    holdings = [Holding(ticker="A", weight=0.05)]
    ips = make_ips(**{"lang": "zh"})
    card = next(c for c in propose(holdings, [], ips, "us") if c.action == "ALERT")
    assert_zh(card)
    assert card.lang == "zh"


@pytest.mark.parametrize("value", ["en", "fr", "de", None])
def test_lang_en_and_unknown_and_absent_give_english_byte_for_byte(value):
    holdings = [Holding(ticker="A", weight=0.05)]
    ips = make_ips()  # default lang "en"
    baseline = next(c for c in propose(holdings, [], ips, "us") if c.action == "ALERT")
    card = next(c for c in propose(holdings, [], ips, "us", lang=value) if c.action == "ALERT")
    assert card.reason == baseline.reason
    assert card.lang == "en"


@pytest.mark.parametrize("value", ["zh", "zh-TW", "zh_TW", "ZH", "ZH_tw"])
def test_lang_zh_variants_give_chinese(value):
    holdings = [Holding(ticker="A", weight=0.05)]
    card = next(
        c for c in propose(holdings, [], make_ips(), "us", lang=value) if c.action == "ALERT"
    )
    assert card.lang == "zh"
    assert_zh(card)


# --- AC #1/#2: to_markdown()'s detail-line labels render in the card's language ----


def test_to_markdown_detail_labels_zh_vs_en():
    holdings = [Holding(ticker="AAA", weight=0.15, score=0.85)]
    ips = make_ips(**{"turnover.hurdle": 0.05})
    en = next(c for c in propose(holdings, [cand("XXX", 0.95)], ips, "us") if c.action == "SWAP")
    zh = next(
        c for c in propose(holdings, [cand("XXX", 0.95)], ips, "us", lang="zh") if c.action == "SWAP"
    )
    en_lines = en.to_markdown().splitlines()
    zh_lines = zh.to_markdown().splitlines()
    assert en_lines[0] == zh_lines[0] == "### SWAP AAA → XXX"
    assert "score gap" in en.to_markdown()
    assert "est. friction" in en.to_markdown()
    assert "per your IPS" in en.to_markdown()
    assert "score gap" not in zh.to_markdown()
    assert "est. friction" not in zh.to_markdown()
    assert "per your IPS" not in zh.to_markdown()
    # the numbers on those lines are unchanged
    assert "+0.100" in zh.to_markdown()  # score gap 0.95 - 0.85
