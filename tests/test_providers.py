"""Provider tests. No network: yf/finmind panel-shaping is factored into pure
functions and exercised with faked frames / fixture JSON, per ARCHITECTURE.md's
"pure compute, thin IO" rule.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kuroshio.providers import get_provider
from kuroshio.providers.finmind import _shape_panel as finmind_shape_panel
from kuroshio.providers.yf import _shape_panel as yf_shape_panel


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
