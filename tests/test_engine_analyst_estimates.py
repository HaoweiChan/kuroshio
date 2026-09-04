"""No-network tests for the T8 engine half: the get_analyst_estimates dataflow
(rendered from a stubbed yf.Ticker) and its wiring into the fundamentals analyst.
"""

from __future__ import annotations

import inspect

import pandas as pd

from kuroshio.agents.engine.agents.analysts import fundamentals_analyst
from kuroshio.agents.engine.dataflows import y_finance


class _StubEstimatesTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    @property
    def earnings_estimate(self):
        return pd.DataFrame({"numberOfAnalysts": [12], "growth": [0.18]}, index=["0y"])

    @property
    def eps_revisions(self):
        return pd.DataFrame(
            {"upLast30days": [9], "downLast30days": [2]}, index=["0y"]
        )

    @property
    def recommendations_summary(self):
        return pd.DataFrame(
            {"period": ["0m"], "strongBuy": [5], "buy": [10], "hold": [3], "sell": [1], "strongSell": [0]}
        )

    @property
    def calendar(self):
        return {"Earnings Date": ["2026-10-15"]}


def test_get_analyst_estimates_renders_revisions_and_next_earnings_date(monkeypatch):
    monkeypatch.setattr(y_finance.yf, "Ticker", _StubEstimatesTicker)

    report = y_finance.get_analyst_estimates("AAPL", "2026-09-04")

    assert "# Analyst Estimates for AAPL" in report
    assert "9" in report  # upLast30days
    assert "2" in report  # downLast30days
    assert "2026-10-15" in report  # next earnings date


def test_fundamentals_analyst_tool_list_includes_estimates_and_insider_tools():
    # Constructing the node needs a real LLM (bind_tools is only called once
    # invoked with state), but the tool list is a local inside the closure, so
    # assert on the source rather than instantiating one.
    src = inspect.getsource(fundamentals_analyst.create_fundamentals_analyst)
    assert "get_analyst_estimates" in src
    assert "get_insider_transactions" in src
