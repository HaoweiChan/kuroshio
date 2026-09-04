"""US default profile: 12-1 momentum.

Single-factor, liquidity-gated-only baseline: no MA/breakout gate by design.
The 2026-09 point-in-time backtest (docs/backtest-2026-09.md) made it the default as
the less bad of the two US screens; it beat SPY in 2021-2026 and lost in 2014-2021.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ...types import Candidate, Panel
from .score import pctrank
from .us import DOLLAR_VOL_MIN, PRICE_MIN, VOL_LB

# --- Tunables ---------------------------------------------------------------
MOM_LB = 252    # momentum lookback, in sessions
MOM_SKIP = 21   # skip the most recent month (avoid short-term reversal)


def _screen_or_score(
    panel: Panel,
    asof: str | None,
    gate: bool,
    benchmark: str = "SPY",
    tickers: Sequence[str] | None = None,
) -> list[Candidate]:
    """Shared pool-build + cross-sectional score for ``screen``/``score_names`` —
    see us.py's ``_screen_or_score`` for the pattern this mirrors."""
    close = panel.close
    if close.empty:
        return []
    asof = asof if asof is not None else str(close.index[-1])
    if asof not in close.index:
        return []
    volume = panel.volume.reindex(close.index)

    avg_vol_ind = volume.shift(1).rolling(VOL_LB).mean()  # excludes today, same as us.py
    mom_skip_close = close.shift(MOM_SKIP)
    mom_lb_close = close.shift(MOM_LB)

    row_close = close.loc[asof]
    avg_vol = avg_vol_ind.loc[asof]
    c_skip = mom_skip_close.loc[asof]
    c_lb = mom_lb_close.loc[asof]

    if tickers is None:
        reference_cols = {benchmark}
        stocks = [s for s in close.columns if s not in reference_cols]
    else:
        stocks = [s for s in tickers if s in close.columns]

    pool: list[dict] = []
    for sym in stocks:
        c, av = row_close.get(sym), avg_vol.get(sym)
        skip_px, lb_px = c_skip.get(sym), c_lb.get(sym)
        if any(pd.isna(x) for x in (c, av, skip_px, lb_px)) or lb_px <= 0:
            continue
        mom_raw = skip_px / lb_px - 1.0
        if gate:
            if c < PRICE_MIN:
                continue
            if av <= 0 or c * av < DOLLAR_VOL_MIN:
                continue
        pool.append({"ticker": sym, "close": c, "mom_raw": mom_raw, "avg_vol": av})

    if not pool:
        return []

    scores = dict(zip((p["ticker"] for p in pool), pctrank([p["mom_raw"] for p in pool])))

    candidates: list[Candidate] = []
    for p in pool:
        sym = p["ticker"]
        final = scores[sym]
        candidates.append(
            Candidate(
                ticker=sym,
                date=asof,
                rank=0,
                final_score=final,
                scores={"mom_12_1": final},
                factors={
                    "close": p["close"],
                    "mom_12_1_raw": p["mom_raw"],
                    "avg_vol": p["avg_vol"],
                },
                flags={},
            )
        )

    candidates.sort(key=lambda c: (-c.final_score, c.ticker))
    for rank, c in enumerate(candidates, start=1):
        c.rank = rank
    return candidates


def screen(panel: Panel, asof: str | None = None, benchmark: str = "SPY") -> list[Candidate]:
    """Stage-1 (liquidity-only) gate + cross-sectional 12-1 momentum score the US
    universe as of ``asof`` (default: the last panel row). Pure — no network, no DB."""
    return _screen_or_score(panel, asof, gate=True, benchmark=benchmark)


def score_names(
    panel: Panel,
    tickers: Sequence[str],
    asof: str | None = None,
    benchmark: str = "SPY",
) -> list[Candidate]:
    """Score every requested ticker with the exact same 12-1 momentum pctrank as
    ``screen`` — but skip the liquidity gate. Same scale as ``screen`` (one
    cross-section per call) — see us.score_names's docstring for the "Fix 2" rationale
    this mirrors: the allocator needs a score for held names that don't clear the gate."""
    return _screen_or_score(panel, asof, gate=False, benchmark=benchmark, tickers=tickers)
