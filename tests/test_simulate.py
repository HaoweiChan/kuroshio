"""No-network tests for kuroshio.core.simulate — synthetic panels only.

Reuses the ascending-constant-rate + flat SPY construction from test_backtest.py:
since growth is a pure exponential at a fixed per-ticker rate, the highest-rate
names are both the highest-momentum (screen-selected) and the best performers, so
the strategy's final holdings are pinned exactly. A second panel (`_dropper_panel`)
adds one ticker that rises steadily, then crashes 30% in 10 sessions, to exercise
the max-adverse-excursion DECIDE path.
"""

from __future__ import annotations

import math

import pandas as pd

from kuroshio.core.screening import us
from kuroshio.core.simulate import simulate
from kuroshio.types import Panel
from tests.test_allocator import make_ips

N = 260
RATES = [0.0006, 0.0010, 0.0014, 0.0018, 0.0022, 0.0026, 0.0030, 0.0034]  # daily, ascending
TICKERS = [f"T{i}" for i in range(len(RATES))]


def _dates(n: int = N) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=n)]


def _ascending_panel() -> Panel:
    dates = _dates()
    close = pd.DataFrame(
        {t: [50.0 * (1.0 + r) ** d for d in range(N)] for t, r in zip(TICKERS, RATES)},
        index=dates,
    )
    close["SPY"] = 100.0
    volume = pd.DataFrame({c: [2_000_000.0] * N for c in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def _dropper_panel() -> Panel:
    """DROPPER out-climbs everything for 220 sessions (so it's the sole top-1 pick at
    the first rebalance, day 210), then loses 30% over the next 10 sessions, then goes
    flat — well past the default caps.max_adverse_excursion_pct of -15%."""
    dates = _dates()
    peak_rate = 0.003
    peak = 50.0 * (1.0 + peak_rate) ** 219
    dropper = []
    for d in range(N):
        if d < 220:
            dropper.append(50.0 * (1.0 + peak_rate) ** d)
        elif d < 230:
            dropper.append(peak * 0.7 ** ((d - 219) / 10))
        else:
            dropper.append(peak * 0.7)

    close = pd.DataFrame(
        {f"F{i}": [50.0 * (1.0 + r) ** d for d in range(N)] for i, r in enumerate([0.0004, 0.0006, 0.0008])},
        index=dates,
    )
    close["DROPPER"] = dropper
    close["SPY"] = 100.0
    volume = pd.DataFrame({c: [2_000_000.0] * N for c in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def _overtaker_panel(n: int = 320) -> Panel:
    """A (0.3%/d) and B (0.2%/d) lead from the start; LATE sits flat for 200 sessions,
    then compounds at 0.6%/d. Momentum is (close/MA50 - 1) + (close/MA200 - 1), so LATE
    needs ~50 rising sessions before its score passes A's — well after the first
    rebalance at session 210, so it enters as a challenger, not an inception buy."""
    dates = _dates(n)
    close = pd.DataFrame(
        {
            "A": [50.0 * 1.003 ** d for d in range(n)],
            "B": [50.0 * 1.002 ** d for d in range(n)],
            "LATE": [50.0 if d < 200 else 50.0 * 1.006 ** (d - 200) for d in range(n)],
        },
        index=dates,
    )
    close["SPY"] = 100.0
    volume = pd.DataFrame({c: [2_000_000.0] * n for c in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def _run(panel=None, **kwargs):
    panel = panel or _ascending_panel()
    ips = kwargs.pop("ips", None) or make_ips()
    return simulate(panel, us.screen, us.score_names, ips, "us", benchmark="SPY", **kwargs)


def test_nav_starts_at_one_and_is_finite():
    result = _run(top_k=5, step=5)
    assert result.nav[0] == 1.0
    assert len(result.nav) == len(result.dates)
    assert all(math.isfinite(v) for v in result.nav)
    assert all(math.isfinite(v) for v in result.ew_nav)
    assert result.bench_nav is not None and all(math.isfinite(v) for v in result.bench_nav)


def test_ascending_panel_holds_the_top_k_raters_and_beats_the_flat_benchmark():
    # top-5 of 8 ascending rates -> T3..T7 dominate momentum every round, so every
    # eligible name is already held from the first rebalance on: no challenger ever
    # exists, so no SWAP ever fires either.
    result = _run(top_k=5, step=5)
    summary = result.summary()
    assert set(summary["final_holdings"]) == {"T3", "T4", "T5", "T6", "T7"}
    assert summary["n_decides"] == 0
    assert result.nav[-1] > result.bench_nav[-1]


def test_a_ticker_past_the_mae_threshold_is_decided_and_absent_afterward():
    result = _run(panel=_dropper_panel(), top_k=1, step=5)
    decides = [t for t in result.trades if t["action"] == "DECIDE" and t["sell"] == "DROPPER"]
    assert len(decides) == 1
    assert "DROPPER" not in result.summary()["final_holdings"]


def test_a_late_leader_swaps_out_the_weakest_incumbent():
    ips = make_ips(**{"caps.position_hard_pct": 100})
    result = _run(panel=_overtaker_panel(), ips=ips, top_k=2, step=5)
    swaps = [t for t in result.trades if t["action"] == "SWAP"]
    assert [(t["sell"], t["buy"]) for t in swaps] == [("B", "LATE")]
    assert set(result.summary()["final_holdings"]) == {"A", "LATE"}
    assert result.summary()["n_decides"] == 0


def test_inception_is_free_and_excluded_from_turnover():
    result = _run(top_k=5, step=5)
    first = [t for t in result.trades if t["date"] == result.dates[0]]
    assert first and all(t["action"] == "BUY" and t["cost"] == 0.0 for t in first)
    later = sum(
        (2 if t["action"] == "SWAP" else 1) * t["weight"]
        for t in result.trades if t["date"] != result.dates[0]
    )
    assert result.summary()["ann_turnover"] == later / (len(result.dates) / 252)


def test_positions_never_exceed_the_hard_cap_right_after_a_rebalance():
    ips = make_ips(**{"caps.position_hard_pct": 5})
    result = _run(ips=ips, top_k=5, step=5)
    assert result.weights  # at least one rebalance ran
    for row in result.weights:
        for ticker, weight in row.items():
            if ticker == "date":
                continue
            assert weight <= 0.05 + 1e-9, (row["date"], ticker, weight)


def test_nonzero_friction_lowers_final_nav_with_the_same_trade_sequence():
    # A tight hard cap (15%, under the 20% equal-weight starting point) forces
    # repeated TRIMs as the fastest of the five held names outgrows its peers —
    # TRIM fires purely on weight vs. cap, never on the friction-loaded swap
    # hurdle, and every eligible name is already held (see the test above), so no
    # SWAP is ever possible either way. That makes the trade sequence identical
    # under any friction while still paying friction on every TRIM leg.
    panel = _ascending_panel()

    def trade_seq(result):
        return [(t["date"], t["action"], t["sell"], t["buy"]) for t in result.trades]

    zero_ips = make_ips(**{"caps.position_hard_pct": 15, "friction.us_roundtrip_pct": 0.0})
    hi_ips = make_ips(**{"caps.position_hard_pct": 15, "friction.us_roundtrip_pct": 1.0})

    zero = _run(panel=panel, ips=zero_ips, top_k=5, step=5)
    hi = _run(panel=panel, ips=hi_ips, top_k=5, step=5)

    assert trade_seq(zero) == trade_seq(hi)
    assert any(t["action"] == "TRIM" for t in zero.trades)  # friction actually gets charged
    assert hi.nav[-1] < zero.nav[-1]


def test_summary_has_expected_keys_and_to_markdown_is_nonempty():
    result = _run(top_k=5, step=5)
    summary = result.summary()
    for key in (
        "total_return", "max_drawdown", "ann_turnover", "n_swaps", "n_trims",
        "n_decides", "ew_total_return", "bench_total_return", "n_rebalances",
    ):
        assert key in summary
    assert result.to_markdown()
