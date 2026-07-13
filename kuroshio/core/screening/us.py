"""US leadership profile.

Ported from a production-validated US screener prototype (``_indicators``
+ ``evaluate``). Point-in-time S&P membership, the congress/13F/polymarket
overlays, the regime report and the backtest are out of scope here (see
ARCHITECTURE.md) — this ports only the Stage-1 gate + factor scoring.

Vectorized like the source: the rolling indicator frames are computed once
over the whole panel, then sliced at the ``asof`` row.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ...types import Candidate, Panel
from .score import pctrank, weighted_score

# --- Tunables (unchanged from the source) ---------------------------------
MA_S, MA_M, MA_L = 20, 50, 200
HIGH_LB = 60          # breakout: close must be a 60-day closing high
VOL_LB = 20           # volume baseline window (before today)
RET_LB = 5            # overheated hard-filter lookback
RET_MAX = 0.25        # drop names up >= +25% over 5 sessions
PRICE_MIN = 5.0
NEAR_HIGH = 0.90      # Stage-1: close must be >= 90% of the 60-day high (leadership)
DOLLAR_VOL_MIN = 25_000_000.0   # liquidity floor: close × avg20 volume ($/day)

# US factor weights, renormalized over whichever factors are available (sum 1 when all present).
WEIGHTS = {"momentum": 0.333, "rs": 0.267, "volume": 0.20, "sector": 0.20}

_FACTOR_KEYS = ("close", "mom_raw", "vol_raw", "rs_raw", "sector_raw")


def _indicators(close: pd.DataFrame, volume: pd.DataFrame) -> dict:
    return {
        "ma_s": close.rolling(MA_S).mean(),
        "ma_m": close.rolling(MA_M).mean(),
        "ma_l": close.rolling(MA_L).mean(),
        "high_hb": close.rolling(HIGH_LB).max(),
        "avg_vol": volume.shift(1).rolling(VOL_LB).mean(),   # excludes today
        "ret5": close.pct_change(RET_LB),
        "ret20": close.pct_change(MA_S),
        "ret60": close.pct_change(HIGH_LB),
    }


def _screen_or_score(
    panel: Panel,
    asof: str | None,
    gate: bool,
    sector_map: dict[str, str] | None = None,
    benchmark: str = "SPY",
    tickers: Sequence[str] | None = None,
) -> list[Candidate]:
    """Shared pool-build + cross-sectional score, used by both ``screen`` (gate=True,
    universe = every non-reference panel column) and ``score_names`` (gate=False,
    universe = the explicit ``tickers``) — see Fix 2's module docstring in
    :func:`score_names`. Identical scoring math either way: the only difference is
    whether Stage-1 filters the pool before ranking.

    ``sector_map`` (ticker -> sector ETF) and ``benchmark`` double as the
    reference-instrument set: any panel column that is the benchmark or a
    sector ETF target is reference data, not a candidate stock.
    """
    close = panel.close
    if close.empty:
        return []
    asof = asof if asof is not None else str(close.index[-1])
    if asof not in close.index:
        return []
    # Row-align volume to close's index — a date missing from panel.volume (e.g. a
    # partial-outage panel) becomes an all-NaN row instead of a KeyError on .loc[asof];
    # those NaNs then flow through the existing per-ticker NaN skip below.
    volume = panel.volume.reindex(close.index)

    ind = _indicators(close, volume)
    row_close = close.loc[asof]
    row_vol = volume.loc[asof]
    ma_s, ma_m, ma_l = ind["ma_s"].loc[asof], ind["ma_m"].loc[asof], ind["ma_l"].loc[asof]
    high_hb = ind["high_hb"].loc[asof]
    avg_vol = ind["avg_vol"].loc[asof]
    ret5 = ind["ret5"].loc[asof]
    ret20 = ind["ret20"].loc[asof]
    ret60 = ind["ret60"].loc[asof]

    b_r20, b_r60 = ret20.get(benchmark), ret60.get(benchmark)
    have_bench = benchmark in close.columns and pd.notna(b_r20) and pd.notna(b_r60)

    sector_etfs = set(sector_map.values()) if sector_map else set()
    etf_rs: dict[str, float] = {}
    if have_bench:
        for etf in sector_etfs:
            if etf in close.columns:
                r20 = ret20.get(etf)
                if pd.notna(r20):
                    etf_rs[etf] = r20 - b_r20

    if tickers is None:
        reference_cols = sector_etfs | {benchmark}
        stocks = [s for s in close.columns if s not in reference_cols]
    else:
        stocks = [s for s in tickers if s in close.columns]

    pool: list[dict] = []
    for sym in stocks:
        c, s, m, lo = row_close.get(sym), ma_s.get(sym), ma_m.get(sym), ma_l.get(sym)
        hb, av, v, r5 = high_hb.get(sym), avg_vol.get(sym), row_vol.get(sym), ret5.get(sym)
        if any(pd.isna(x) for x in (c, s, m, lo, hb, av, v, r5)):
            continue
        # --- Stage 1: must pass ALL (skipped when gate=False — Fix 2, see score_names) ---
        if gate:
            if not (c > s > m > lo):            # stacked-MA uptrend
                continue
            if c < NEAR_HIGH * hb:              # within (1-NEAR_HIGH) of the 60d high
                continue
            if r5 >= RET_MAX or c < PRICE_MIN:  # overheated / penny hard-filters
                continue
            if av <= 0 or c * av < DOLLAR_VOL_MIN:  # liquidity floor
                continue

        raw = {
            "ticker": sym,
            "close": c,
            "mom_raw": (c / m - 1.0) + (c / lo - 1.0),
            "vol_raw": v / av,
            "is_60d_high": bool(c >= hb),
        }
        if have_bench:
            r20_sym, r60_sym = ret20.get(sym), ret60.get(sym)
            if pd.notna(r20_sym) and pd.notna(r60_sym):
                raw["rs_raw"] = (r20_sym - b_r20) + (r60_sym - b_r60)
        etf = sector_map.get(sym) if sector_map else None
        if etf is not None and etf in etf_rs:
            raw["sector_raw"] = etf_rs[etf]
        pool.append(raw)

    if not pool:
        return []

    def _ranked(key: str) -> dict[str, float]:
        sub = [p for p in pool if key in p]
        return dict(zip((p["ticker"] for p in sub), pctrank([p[key] for p in sub])))

    mom_scores = _ranked("mom_raw")
    vol_scores = _ranked("vol_raw")
    rs_scores = _ranked("rs_raw")
    sector_scores = _ranked("sector_raw")

    candidates: list[Candidate] = []
    for p in pool:
        sym = p["ticker"]
        scores = {"momentum": mom_scores[sym], "volume": vol_scores[sym]}
        if sym in rs_scores:
            scores["rs"] = rs_scores[sym]
        if sym in sector_scores:
            scores["sector"] = sector_scores[sym]
        final = weighted_score(scores, WEIGHTS)
        factors = {k: p[k] for k in _FACTOR_KEYS if k in p}
        candidates.append(
            Candidate(
                ticker=sym,
                date=asof,
                rank=0,
                final_score=final,
                scores=scores,
                factors=factors,
                flags={"is_60d_high": p["is_60d_high"]},
            )
        )

    candidates.sort(key=lambda c: (-c.final_score, c.ticker))
    for rank, c in enumerate(candidates, start=1):
        c.rank = rank
    return candidates


def screen(
    panel: Panel,
    asof: str | None = None,
    sector_map: dict[str, str] | None = None,
    benchmark: str = "SPY",
) -> list[Candidate]:
    """Stage-1 gate + cross-sectional score the US universe as of ``asof``
    (default: the last panel row). Pure — no network, no DB."""
    return _screen_or_score(panel, asof, gate=True, sector_map=sector_map, benchmark=benchmark)


def score_names(
    panel: Panel,
    tickers: Sequence[str],
    asof: str | None = None,
    sector_map: dict[str, str] | None = None,
    benchmark: str = "SPY",
) -> list[Candidate]:
    """Score every requested ticker with the exact same factor weights/pctrank/
    weighted_score as ``screen`` — but skip the Stage-1 breakout gate.

    Fix 2 (kuroshio<->hermes glue): the allocator can only rank an incumbent as
    "weakest" if it has a score, but ``screen``'s Stage-1 gate only passes names
    in a stacked-MA uptrend near a 60-day high — on a day where a held name isn't
    leading, it gets no score and the allocator silently can't propose a swap
    against it. This is deliberately the SAME scoring path as ``screen`` (just
    gate=False) so a challenger's ``final_score`` and an incumbent's ``score``
    stay comparable on the same scale; do not fork a separate ranking formula here.
    """
    return _screen_or_score(panel, asof, gate=False, sector_map=sector_map, benchmark=benchmark, tickers=tickers)
