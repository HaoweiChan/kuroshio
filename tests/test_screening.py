"""No-network tests for kuroshio.core.screening — synthetic panels only."""

from __future__ import annotations

import pandas as pd
import pytest

from kuroshio.core.screening import get_profile, pctrank, tw, us
from kuroshio.providers import _REGISTRY as _PROVIDER_REGISTRY
from kuroshio.types import Panel

N = 210  # long enough for the US profile's MA200; plenty of slack for TW's MA60


def _dates(n: int = N) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=n)]


def _up(n: int = N, lo: float = 50.0, hi: float = 120.0) -> list[float]:
    return list(pd.Series(range(n)).map(lambda i: lo + (hi - lo) * i / (n - 1)))


def _down(n: int = N, hi: float = 120.0, lo: float = 60.0) -> list[float]:
    return list(pd.Series(range(n)).map(lambda i: hi - (hi - lo) * i / (n - 1)))


# --- pctrank -----------------------------------------------------------------
def test_pctrank_ties_match_source_semantics():
    # average-rank ties: 1 < (2,2 tied) < 3 -> ranks 0, 1.5, 1.5, 3 scaled by /(n-1)
    assert pctrank([1, 2, 2, 3]) == pytest.approx([0.0, 0.5, 0.5, 1.0])


def test_pctrank_n_lte_1_is_zero():
    assert pctrank([5.0]) == [0.0]
    assert pctrank([]) == []


# --- TW ------------------------------------------------------------------
def _tw_panel(with_institutional: bool) -> Panel:
    dates = _dates()
    tickers = ["1101", "1102", "1103", "0050"]
    close = pd.DataFrame(
        {
            "1101": _up(hi=150.0),   # strong breakout
            "1102": _up(hi=80.0),    # weaker breakout, still passes
            "1103": _down(),         # downtrend -> rejected
            "0050": _up(hi=150.0),   # ETF ticker -> excluded by passes_universe regardless of data
        },
        index=dates,
    )
    volume = pd.DataFrame({t: [1_000_000.0] * N for t in tickers}, index=dates)
    volume.loc[dates[-1], "1101"] = 3_000_000.0   # 3x baseline -> clears VOL_MULT_MIN
    volume.loc[dates[-1], "1102"] = 1_800_000.0   # 1.8x baseline -> just clears it
    volume.loc[dates[-1], "0050"] = 3_000_000.0

    institutional = None
    if with_institutional:
        institutional = pd.DataFrame(
            {
                "1101": [500_000.0] * N,   # heavy net buying
                "1102": [50_000.0] * N,    # light net buying
                "1103": [0.0] * N,
                "0050": [0.0] * N,
            },
            index=dates,
        )
    return Panel(close=close, volume=volume, institutional=institutional)


def test_tw_screen_ranks_and_excludes_universe():
    panel = _tw_panel(with_institutional=True)
    candidates = tw.screen(panel)
    tickers = {c.ticker for c in candidates}

    assert "1101" in tickers
    assert "1102" in tickers
    assert "1103" not in tickers  # downtrend
    assert "0050" not in tickers  # ETF, excluded by passes_universe

    by_ticker = {c.ticker: c for c in candidates}
    strong, weak = by_ticker["1101"], by_ticker["1102"]
    assert strong.final_score > weak.final_score
    assert strong.rank < weak.rank
    for c in (strong, weak):
        assert 0.0 <= c.final_score <= 1.0
        assert c.flags["degraded"] is False
        assert "institution" in c.scores


def test_tw_screen_degrades_without_institutional():
    panel = _tw_panel(with_institutional=False)
    candidates = tw.screen(panel)
    assert candidates  # 1101/1102 still pass Stage 1
    for c in candidates:
        assert c.flags["degraded"] is True
        assert "institution" not in c.scores
        assert 0.0 <= c.final_score <= 1.0
        # weight renormalizes to momentum-only -> final == momentum exactly
        assert c.final_score == pytest.approx(c.scores["momentum"])


def test_tw_screen_degrades_when_institutional_frame_empty():
    # Total-outage frame: present (not None) but zero columns -> same treatment as None.
    panel = _tw_panel(with_institutional=True)
    panel.institutional = panel.institutional.drop(columns=list(panel.institutional.columns))
    assert panel.institutional.empty

    candidates = tw.screen(panel)
    assert candidates
    for c in candidates:
        assert c.flags["degraded"] is True
        assert "institution" not in c.scores
        assert 0.0 <= c.final_score <= 1.0


def test_tw_screen_missing_ticker_column_degrades_only_that_candidate():
    # Institutional frame is present and healthy, but 1102 has no column in it
    # (e.g. FinMind returned nothing for that one ticker) -> only 1102 degrades;
    # its institution_raw must not be fabricated as 0.0 and pctranked against
    # tickers with real data.
    panel = _tw_panel(with_institutional=True)
    panel.institutional = panel.institutional.drop(columns=["1102"])

    candidates = tw.screen(panel)
    by_ticker = {c.ticker: c for c in candidates}
    assert set(by_ticker) == {"1101", "1102"}

    strong = by_ticker["1101"]
    assert strong.flags["degraded"] is False
    assert "institution" in strong.scores

    missing = by_ticker["1102"]
    assert missing.flags["degraded"] is True
    assert "institution" not in missing.scores

    for c in candidates:
        assert 0.0 <= c.final_score <= 1.0


def test_tw_screen_excludes_ticker_with_volume_nan_in_window():
    # A NaN anywhere in the 60-session volume window must exclude the ticker
    # entirely, not get fillna(0)'d (which would deflate the baseline and
    # inflate vol_mult past the 1.5x gate).
    panel = _tw_panel(with_institutional=True)
    dates = panel.close.index
    panel.volume.loc[dates[-10], "1101"] = float("nan")

    candidates = tw.screen(panel)
    tickers = {c.ticker for c in candidates}
    assert "1101" not in tickers
    assert "1102" in tickers  # unaffected ticker still passes


# --- US --------------------------------------------------------------------
def _us_panel() -> Panel:
    dates = _dates()
    close = pd.DataFrame(
        {
            "AMD": _up(),                 # uptrend -> passes
            "XOM": _down(),                # downtrend -> rejected
            "SPY": [100.0] * N,            # flat benchmark
            "SMH": _up(lo=40.0, hi=90.0),  # sector ETF, also uptrending
        },
        index=dates,
    )
    volume = pd.DataFrame({t: [1e7] * N for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def test_us_screen_passes_uptrend_rejects_downtrend():
    panel = _us_panel()
    candidates = us.screen(panel, sector_map={"AMD": "SMH"})
    tickers = {c.ticker for c in candidates}

    assert "AMD" in tickers
    assert "XOM" not in tickers   # downtrend
    assert "SPY" not in tickers   # benchmark is reference data, not a candidate
    assert "SMH" not in tickers   # sector ETF is reference data, not a candidate

    amd = next(c for c in candidates if c.ticker == "AMD")
    assert 0.0 <= amd.final_score <= 1.0
    assert set(amd.scores) == {"momentum", "rs", "volume", "sector"}


def test_us_screen_missing_sector_map_drops_sector_factor():
    panel = _us_panel()
    candidates = us.screen(panel, sector_map=None)
    amd = next(c for c in candidates if c.ticker == "AMD")
    assert "sector" not in amd.scores
    assert set(amd.scores) == {"momentum", "rs", "volume"}
    assert 0.0 <= amd.final_score <= 1.0


def test_us_screen_asof_missing_from_volume_index_no_crash():
    # asof (the latest close date) has no row in panel.volume at all -> must not
    # KeyError on ind["avg_vol"].loc[asof]; the row-aligned reindex turns the
    # missing date into an all-NaN row, which the per-ticker NaN skip handles.
    panel = _us_panel()
    panel.volume = panel.volume.iloc[:-1]

    candidates = us.screen(panel, sector_map={"AMD": "SMH"})
    assert isinstance(candidates, list)


# --- market registry -----------------------------------------------------------


@pytest.mark.parametrize("market", ["us", "tw"])
def test_get_profile_returns_working_profile(market):
    profile = get_profile(market)
    assert profile.name == market
    assert callable(profile.screen)
    # Resolvable at the provider registry level (no ImportError from a missing
    # optional SDK — this only checks the name is known, not that it imports).
    assert profile.default_provider in _PROVIDER_REGISTRY


def test_get_profile_unknown_market_raises():
    with pytest.raises(ValueError) as exc:
        get_profile("jp")
    message = str(exc.value)
    assert "us" in message and "tw" in message
