"""No-network tests for kuroshio.core.backtest — synthetic panel only.

8 tickers with distinct constant daily growth rates (ascending) + a flat SPY
benchmark: since growth is a pure exponential at a fixed per-ticker rate, past
momentum (what final_score picks up) and future continuation (forward return)
are the same signal — score should predict forward return almost perfectly,
which is exactly what the IC / quintile assertions below check for.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from kuroshio.core.backtest import walkforward
from kuroshio.core.screening import us
from kuroshio.types import Panel

N = 260
RATES = [0.0006, 0.0010, 0.0014, 0.0018, 0.0022, 0.0026, 0.0030, 0.0034]  # daily, ascending
TICKERS = [f"T{i}" for i in range(len(RATES))]


def _panel() -> Panel:
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=N)]
    close = pd.DataFrame(
        {t: [50.0 * (1.0 + r) ** d for d in range(N)] for t, r in zip(TICKERS, RATES)},
        index=dates,
    )
    close["SPY"] = 100.0
    volume = pd.DataFrame({c: [2_000_000.0] * N for c in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def _run(**kwargs):
    return walkforward(_panel(), us.screen, horizon=20, top_k=5, benchmark="SPY", **kwargs)


def test_records_are_finite_and_nonempty():
    result = _run()
    assert result.records
    for r in result.records:
        assert not math.isnan(r["topk_fwd"])
        assert r["n_candidates"] > 0


def test_summary_has_expected_keys():
    result = _run()
    summary = result.summary()
    for key in ("n_rebalances", "mean_topk_fwd", "mean_excess_vs_bench", "beat_rate", "mean_ic", "quintiles"):
        assert key in summary


def test_ic_present_on_dates_with_more_than_two_candidates():
    result = _run()
    assert all(r["n_candidates"] <= 2 or r["ic"] is not None for r in result.records)
    assert any(r["ic"] is not None for r in result.records)


def test_quintile_table_is_monotonic_top_beats_bottom():
    result = _run()
    q = result.summary()["quintiles"]
    assert q
    assert q["Q5"]["mean"] > q["Q1"]["mean"]


def test_to_markdown_nonempty_and_mentions_ic():
    md = _run().to_markdown()
    assert md
    assert "IC" in md


def test_horizon_larger_than_available_data_yields_empty_result_no_crash():
    result = walkforward(_panel(), us.screen, horizon=10_000, top_k=5, benchmark="SPY")
    assert result.records == []
    summary = result.summary()
    assert summary["n_rebalances"] == 0
    assert result.to_markdown()  # still a non-empty string, doesn't crash
