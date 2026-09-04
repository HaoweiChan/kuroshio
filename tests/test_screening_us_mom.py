"""No-network tests for kuroshio.core.screening.us_mom — synthetic panels only."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from kuroshio.core.screening import get_profile, us, us_mom
from kuroshio.types import Panel

N = 300  # > MOM_LB(252) + slack
VOL = 2_000_000.0


def _dates(n: int = N) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=n)]


def _const_rate(n: int, rate: float, base: float = 100.0) -> list[float]:
    return [base * (1.0 + rate) ** i for i in range(n)]


def _flat_then_jump(n: int, flat_days: int, jump_mult: float, base: float = 100.0) -> list[float]:
    return [base] * flat_days + [base * jump_mult] * (n - flat_days)


def _nan_prefix_flat(n: int, nan_days: int, base: float = 100.0) -> list[float]:
    return [math.nan] * nan_days + [base] * (n - nan_days)


def _panel() -> Panel:
    dates = _dates()
    close = pd.DataFrame(
        {
            "FAST": _const_rate(N, 0.004),      # fastest steady climber
            "MED": _const_rate(N, 0.002),       # medium steady climber
            "SLOW": _const_rate(N, 0.0005),     # slowest steady climber
            "STEADY": _const_rate(N, 0.001),    # modest, steady the whole window
            "JUMPY": _flat_then_jump(N, 279, 1.5),  # flat, then +50% only in the last 21 sessions
            "PENNY": [2.0] * N,                 # fails price floor
            "SHORT": _nan_prefix_flat(N, 100),  # < 252 sessions of history
            "SPY": [100.0] * N,                 # flat benchmark
        },
        index=dates,
    )
    volume = pd.DataFrame({t: [VOL] * N for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


# --- ranking ---------------------------------------------------------------
def test_screen_ranks_by_12_1_momentum_descending():
    panel = _panel()
    candidates = us_mom.screen(panel)
    by_ticker = {c.ticker: c for c in candidates}

    assert {"FAST", "MED", "SLOW"} <= set(by_ticker)
    fast, med, slow = by_ticker["FAST"], by_ticker["MED"], by_ticker["SLOW"]
    assert fast.final_score > med.final_score > slow.final_score
    assert fast.rank < med.rank < slow.rank

    for c in candidates:
        assert 0.0 <= c.final_score <= 1.0
    assert candidates[0].ticker == "FAST"
    assert candidates[0].rank == 1


# --- skip-month behavior -----------------------------------------------------
def test_skip_month_ignores_gain_confined_to_last_21_sessions():
    panel = _panel()
    candidates = us_mom.screen(panel)
    by_ticker = {c.ticker: c for c in candidates}

    assert "STEADY" in by_ticker
    assert "JUMPY" in by_ticker
    # JUMPY's +50% happened entirely inside the skipped last-month window, so its
    # 12-1 momentum is ~flat -- well below STEADY's modest-but-sustained climb.
    assert by_ticker["JUMPY"].final_score < by_ticker["STEADY"].final_score
    assert by_ticker["JUMPY"].factors["mom_12_1_raw"] == pytest.approx(0.0, abs=1e-9)


# --- liquidity gate ----------------------------------------------------------
def test_liquidity_gate_excludes_from_screen_but_not_score_names():
    panel = _panel()
    screened = {c.ticker for c in us_mom.screen(panel)}
    assert "PENNY" not in screened

    scored = us_mom.score_names(panel, tickers=["PENNY", "FAST"])
    assert {c.ticker for c in scored} == {"PENNY", "FAST"}


# --- insufficient history -----------------------------------------------------
def test_insufficient_history_skips_without_exception():
    panel = _panel()
    screened = {c.ticker for c in us_mom.screen(panel)}
    assert "SHORT" not in screened

    scored = us_mom.score_names(panel, tickers=["SHORT"])
    assert scored == []


# --- benchmark + registry -----------------------------------------------------
def test_spy_never_a_candidate():
    panel = _panel()
    tickers = {c.ticker for c in us_mom.screen(panel)}
    assert "SPY" not in tickers


def test_get_profile_us_is_12_1_momentum():
    profile = get_profile("us")
    assert profile.name == "us"
    assert profile.benchmark == "SPY"
    assert profile.min_history == 260
    assert profile.accepts_sector_map is False
    assert profile.screen is us_mom.screen
    assert callable(profile.score_names)

    leadership = get_profile("us-leadership")
    assert leadership.screen is us.screen
    assert leadership.accepts_sector_map is True
