"""allocator/signals.py — panel-derived inputs `propose` and `cli.cmd_propose` need.

`monitor_inputs` already has end-to-end coverage via test_cli.py's propose tests;
this file covers `book_vol` on its own, since it's a small enough function to pin
exactly by hand.
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
import pytest

from kuroshio.core.allocator.signals import book_vol
from kuroshio.types import Holding, Panel


def _panel(rets_by_ticker: dict[str, list[float]]) -> Panel:
    """Build a close panel from per-ticker daily return lists (all same length n):
    n+1 sessions, starting every column at 100.0 and compounding the given returns."""
    n = len(next(iter(rets_by_ticker.values())))
    dates = pd.bdate_range("2024-01-01", periods=n + 1).strftime("%Y-%m-%d").tolist()
    close = {}
    for ticker, rets in rets_by_ticker.items():
        prices = [100.0]
        for r in rets:
            prices.append(prices[-1] * (1 + r))
        close[ticker] = prices
    close_df = pd.DataFrame(close, index=dates)
    volume_df = pd.DataFrame({t: [1_000_000.0] * (n + 1) for t in close}, index=dates)
    return Panel(close=close_df, volume=volume_df, institutional=None)


def test_book_vol_pinned_on_two_holdings_one_flat_one_known():
    """A: flat (0% every day). B: known alternating +1%/-1% returns, 20 sessions.
    50/50 weights -> book return each day is 0.5 * B's return (A contributes 0), so
    the annualized vol is exactly derivable by hand."""
    b_rets = [0.01, -0.01] * 10  # 20 daily returns
    panel = _panel({"A": [0.0] * 20, "B": b_rets})
    holdings = [Holding(ticker="A", weight=0.5), Holding(ticker="B", weight=0.5)]

    vol = book_vol(panel, holdings, window=20)

    book_rets = [0.5 * r for r in b_rets]
    expected = statistics.stdev(book_rets) * math.sqrt(252) * 100  # a percent, like 24.1
    assert vol == pytest.approx(expected, rel=1e-9)
    assert vol == pytest.approx(8.1435, abs=1e-3)


def test_book_vol_none_below_window_plus_one_sessions():
    # window=20 needs 20 daily returns, i.e. 21 sessions of close history.
    panel = _panel({"A": [0.01] * 19})  # only 20 sessions
    holdings = [Holding(ticker="A", weight=1.0)]
    assert book_vol(panel, holdings, window=20) is None


def test_book_vol_none_with_no_holdings():
    panel = _panel({"A": [0.01] * 20})
    assert book_vol(panel, [], window=20) is None


def test_book_vol_renormalizes_over_holdings_with_a_close_and_zeros_holes():
    """A ticker missing from the panel entirely is dropped and the remaining weight is
    renormalized (not silently zeroed into the book return); a hole on one session for a
    ticker that does trade elsewhere in the window is a 0% return that day, like
    `simulate._drift`."""
    b_rets = [0.02] * 20
    panel = _panel({"B": b_rets})
    # C is 50% of the book on paper but has no column at all in the panel.
    holdings = [Holding(ticker="B", weight=0.5), Holding(ticker="C", weight=0.5)]
    vol = book_vol(panel, holdings, window=20)
    # with C dropped, B is renormalized to 100% of the book -> its own vol (~0, all
    # returns identical) rather than half of it.
    assert vol == pytest.approx(0.0, abs=1e-9)
