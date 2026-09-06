"""Provider tests. No network: yf/finmind panel-shaping is factored into pure
functions and exercised with faked frames / fixture JSON, per ARCHITECTURE.md's
"pure compute, thin IO" rule.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kuroshio.providers import get_provider
from kuroshio.providers.finmind import _shape_panel as finmind_shape_panel
from kuroshio.providers.yf import (
    _earnings_estimate_fields,
    _eps_revisions_fields,
    _insider_net_shares_90d,
    _last_surprise_pct,
    _next_earnings_date,
    _recommendations_fields,
)
from kuroshio.providers.yf import (
    _shape_panel as yf_shape_panel,
)


def test_get_provider_returns_known_providers():
    assert get_provider("yfinance").name == "yfinance"
    assert get_provider("finmind").name == "finmind"


def test_get_provider_unknown_name_lists_known_names():
    with pytest.raises(ValueError, match="finmind.*yfinance|yfinance.*finmind"):
        get_provider("bogus")


def test_yf_shape_panel_drops_unresolved_ticker_and_partial_bar():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    raw_close = pd.DataFrame(
        {
            "AAPL": [100.0, 101.0, float("nan")],  # today's bar still forming
            "MSFT": [200.0, 202.0, 205.0],
            "DELISTED": [float("nan"), float("nan"), float("nan")],  # unresolved ticker
        },
        index=dates,
    )
    raw_volume = pd.DataFrame(
        {
            "AAPL": [1000, 1100, 1200],
            "MSFT": [2000, 2100, 2200],
            "DELISTED": [float("nan"), float("nan"), float("nan")],
        },
        index=dates,
    )

    panel = yf_shape_panel(raw_close, raw_volume, tickers=["AAPL", "MSFT", "DELISTED"])

    assert list(panel.close.columns) == ["AAPL", "MSFT"]
    assert list(panel.close.index) == ["2024-01-01", "2024-01-02"]
    assert panel.close.loc["2024-01-02", "AAPL"] == 101.0
    assert list(panel.volume.columns) == ["AAPL", "MSFT"]
    assert panel.institutional is None


def test_finmind_shape_panel_builds_close_volume_and_institutional_net():
    price_by_ticker = {
        "2330": [
            {"date": "2024-01-02", "stock_id": "2330", "close": 590.0, "Trading_Volume": 30000000},
            {"date": "2024-01-03", "stock_id": "2330", "close": 595.0, "Trading_Volume": 31000000},
        ],
        "2454": [],  # no data returned for this ticker
    }
    institutional_by_ticker = {
        "2330": [
            {
                "date": "2024-01-02",
                "stock_id": "2330",
                "name": "Foreign_Investor",
                "buy": 5000000,
                "sell": 3000000,
            },
            {
                "date": "2024-01-02",
                "stock_id": "2330",
                "name": "Investment_Trust",
                "buy": 500000,
                "sell": 200000,
            },
            {"date": "2024-01-02", "stock_id": "2330", "name": "Dealer_self", "buy": 100000, "sell": 900000},
            {
                "date": "2024-01-03",
                "stock_id": "2330",
                "name": "Foreign_Investor",
                "buy": 1000000,
                "sell": 4000000,
            },
        ],
        "2454": [],
    }

    panel = finmind_shape_panel(price_by_ticker, institutional_by_ticker)

    assert list(panel.close.columns) == ["2330"]
    assert list(panel.close.index) == ["2024-01-02", "2024-01-03"]
    assert panel.close.loc["2024-01-02", "2330"] == 590.0
    assert panel.volume.loc["2024-01-03", "2330"] == 31000000
    # net = (foreign buy-sell) + (trust buy-sell); dealer_self excluded
    assert panel.institutional.loc["2024-01-02", "2330"] == (5000000 - 3000000) + (500000 - 200000)
    assert panel.institutional.loc["2024-01-03", "2330"] == 1000000 - 4000000


# --- fetch_fundamentals: estimates/revisions/insider helpers (T8) ---------------


def test_eps_revisions_fields_reads_0y_row():
    table = pd.DataFrame(
        {"upLast7days": [1, 2], "upLast30days": [5, 8], "downLast30days": [2, 3], "downLast7Days": [0, 1]},
        index=["0q", "0y"],
    )
    assert _eps_revisions_fields(table) == (8, 3)
    assert _eps_revisions_fields(None) == (None, None)
    assert _eps_revisions_fields(pd.DataFrame()) == (None, None)
    assert _eps_revisions_fields(table.drop(index="0y")) == (None, None)


def test_earnings_estimate_fields_reads_0y_row():
    table = pd.DataFrame(
        {"numberOfAnalysts": [10, 20], "growth": [0.1, 0.25]}, index=["0q", "0y"]
    )
    assert _earnings_estimate_fields(table) == (0.25, 20)
    assert _earnings_estimate_fields(None) == (None, None)


def test_recommendations_fields_reads_0m_row():
    table = pd.DataFrame(
        {
            "period": ["0m", "-1m"],
            "strongBuy": [5, 4], "buy": [10, 9], "hold": [3, 3],
            "sell": [1, 1], "strongSell": [0, 0],
        }
    )
    assert _recommendations_fields(table) == (15, 3, 1)
    assert _recommendations_fields(None) == (None, None, None)
    assert _recommendations_fields(table[table["period"] == "-1m"]) == (None, None, None)


def test_next_earnings_date_is_first_calendar_entry_as_iso():
    import datetime

    assert _next_earnings_date(
        {"Earnings Date": [datetime.date(2026, 10, 1), datetime.date(2026, 10, 2)]}
    ) == "2026-10-01"
    assert _next_earnings_date({}) is None
    assert _next_earnings_date(None) is None
    assert _next_earnings_date({"Earnings Date": []}) is None


def test_last_surprise_pct_skips_future_rows_with_no_reported_eps():
    idx = pd.to_datetime(["2026-06-01", "2026-09-01", "2026-12-01"])
    table = pd.DataFrame(
        {
            "Reported EPS": [0.9, 1.15, float("nan")],  # 2026-12-01 hasn't reported yet
            "Surprise(%)": [-10.0, 4.5, float("nan")],
        },
        index=idx,
    )
    assert _last_surprise_pct(table) == pytest.approx(4.5)
    assert _last_surprise_pct(None) is None
    assert _last_surprise_pct(pd.DataFrame()) is None


def test_insider_net_shares_90d_counts_purchase_and_sale_within_window():
    today = pd.Timestamp("2026-09-04")
    table = pd.DataFrame(
        {
            "Shares": [1000, 500, 200, 10000],
            "Text": [
                "Purchase at price 10 per share.",
                "Sale at price 12 per share.",
                "Purchase at price 9 per share.",  # outside the 90d window
                "Sale at price 20 per share.",
            ],
            "Start Date": [
                pd.Timestamp("2026-08-20"),
                pd.Timestamp("2026-08-25"),
                pd.Timestamp("2026-01-01"),
                pd.Timestamp("2026-09-01"),
            ],
        }
    )
    # in-window: +1000 (purchase) - 500 - 10000 (sales) = -9500
    assert _insider_net_shares_90d(table, today=today) == -9500
    assert _insider_net_shares_90d(None) is None
    assert _insider_net_shares_90d(pd.DataFrame()) is None

    no_qualifying = pd.DataFrame(
        {
            "Shares": [100],
            "Text": ["Conversion of exercised options."],
            "Start Date": [pd.Timestamp("2026-08-01")],
        }
    )
    assert _insider_net_shares_90d(no_qualifying, today=today) == 0


class _StubEstimatesTicker:
    """Every property is a separate HTTP call in real yfinance; earnings_estimate
    raises here to prove one failing table doesn't blank the others."""

    def __init__(self, ticker):
        self.ticker = ticker

    @property
    def info(self):
        return {"forwardPE": 20.0}

    @property
    def eps_revisions(self):
        return pd.DataFrame({"upLast30days": [8], "downLast30days": [3]}, index=["0y"])

    @property
    def earnings_estimate(self):
        raise RuntimeError("rate limited")

    @property
    def recommendations_summary(self):
        return pd.DataFrame(
            {"period": ["0m"], "strongBuy": [5], "buy": [10], "hold": [3], "sell": [1], "strongSell": [0]}
        )

    @property
    def calendar(self):
        return {}

    @property
    def earnings_dates(self):
        return pd.DataFrame()

    @property
    def insider_transactions(self):
        return None


def test_fetch_fundamentals_wraps_each_table_independently(monkeypatch):
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", _StubEstimatesTicker)

    snap = get_provider("yfinance").fetch_fundamentals("AAA")

    assert snap["forward_pe"] == 20.0
    assert snap["eps_rev_up_30d"] == 8
    assert snap["eps_rev_down_30d"] == 3
    # earnings_estimate raised -> both None, other tables unaffected
    assert snap["eps_est_growth_fy"] is None
    assert snap["n_analysts"] is None
    assert snap["rec_buy"] == 15
    assert snap["rec_hold"] == 3
    assert snap["rec_sell"] == 1
    assert snap["next_earnings_date"] is None
    assert snap["last_surprise_pct"] is None
    assert snap["insider_net_shares_90d"] is None


def test_yf_shape_panel_carries_high_and_low(tmp_path):
    """TASK-11 #1: the OHLC bars yf already downloads reach the Panel, on the same
    index and columns as close — an ATR needs the true range, not just the close."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    frame = lambda vals: pd.DataFrame(  # noqa: E731
        {"AAPL": vals, "DELISTED": [float("nan")] * 3}, index=dates
    )
    panel = yf_shape_panel(
        frame([100.0, 101.0, float("nan")]),
        frame([1000.0, 1100.0, 1200.0]),
        tickers=["AAPL", "DELISTED"],
        raw_high=frame([102.0, 103.0, 104.0]),
        raw_low=frame([99.0, 98.0, 97.0]),
    )
    assert list(panel.high.columns) == ["AAPL"]
    assert list(panel.high.index) == ["2024-01-01", "2024-01-02"]
    assert panel.high.loc["2024-01-02", "AAPL"] == 103.0
    assert panel.low.loc["2024-01-02", "AAPL"] == 98.0


def test_finmind_shape_panel_carries_high_and_low():
    """TASK-11 #1: FinMind's `max`/`min` are the session high/low."""
    price_by_ticker = {
        "2330": [
            {"date": "2024-01-02", "close": 590.0, "max": 595.0, "min": 585.0,
             "Trading_Volume": 30000000},
            {"date": "2024-01-03", "close": 595.0, "max": 600.0, "min": 588.0,
             "Trading_Volume": 31000000},
        ],
    }
    panel = finmind_shape_panel(price_by_ticker, {})
    assert panel.high.loc["2024-01-03", "2330"] == 600.0
    assert panel.low.loc["2024-01-02", "2330"] == 585.0
