"""TW momentum-breakout profile.

Ported from the maintainer's production TW screener: ``passes_universe``,
``compute_stage1_metrics``, ``score_pool``. Only the DB plumbing changed —
inputs now come from a :class:`~kuroshio.types.Panel` instead of SQLAlchemy
queries against ``stock_daily_ohlc`` / ``stock_institutional_daily``.
"""

from __future__ import annotations

import re
from typing import Sequence

from ...types import Candidate, Panel
from .score import pctrank, weighted_score

# --- Tunables (unchanged from the production source) ----------------------
MA_SHORT = 20
MA_LONG = 60
HIGH_SHORT = 20
HIGH_LONG = 60
VOL_BASELINE = 20          # sessions BEFORE today for the volume baseline
VOL_MULT_MIN = 1.5         # today_volume must exceed this × baseline mean
RET_LOOKBACK = 5           # sessions ago for the overheated hard-filter
RET_MAX = 0.20             # drop names up >= +20% over 5 sessions
INSTITUTION_LOOKBACK = 5   # sessions summed for the concentration numerator
CROWDED_THRESHOLD = 70.0   # price_pos_60d above this flags crowded
MIN_SESSIONS = MA_LONG     # MA60 / 60d-high need 60 sessions of history

WEIGHTS = {"momentum": 0.5, "institution": 0.5}

_UNIVERSE_RE = re.compile(r"^\d{4}$")

_FACTOR_KEYS = (
    "close", "ma20", "ma60", "close_ma20", "close_ma60", "vol_mult",
    "mean20_vol_before", "mean20_vol", "today_volume", "institution_raw",
    "price_pos_60d", "ret_5d", "high_20", "high_60", "low_60",
)


def passes_universe(ticker: str) -> bool:
    """Individual-stock universe filter.

    Ticker must be exactly 4 digits, NOT starting with ``00`` (excludes ETFs),
    and contain no letters (excludes warrants). TWSE + TPEx both qualify.
    """
    t = (ticker or "").strip().upper().split(".")[0]  # tolerate a "2330.TW" suffix
    if not _UNIVERSE_RE.match(t):
        return False
    if t.startswith("00"):
        return False
    return True


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute_stage1_metrics(
    dates: Sequence[str], closes: Sequence[float], volumes: Sequence[float]
) -> dict | None:
    """Raw per-ticker metrics for the last day of ``dates`` + Stage-1 breakout filter.

    ``dates``/``closes``/``volumes`` are chronological (oldest→newest), ending on
    the target trading day. Returns a metrics dict when the ticker passes ALL
    Stage-1 gates, else ``None`` (also ``None`` when there is not enough history).
    Institutional concentration is scored separately by ``screen`` — it's a
    factor, not a Stage-1 gate.
    """
    n = len(closes)
    if n < MIN_SESSIONS or n != len(dates) or n != len(volumes):
        return None
    # Need a full baseline window BEFORE today.
    if n < VOL_BASELINE + 1 or n < RET_LOOKBACK + 1:
        return None

    close = closes[-1]
    ma20 = _mean(closes[-MA_SHORT:])
    ma60 = _mean(closes[-MA_LONG:])
    high20 = max(closes[-HIGH_SHORT:])
    high60 = max(closes[-HIGH_LONG:])
    low60 = min(closes[-HIGH_LONG:])
    today_volume = volumes[-1]
    mean20_vol_before = _mean(volumes[-(VOL_BASELINE + 1):-1])  # 20 sessions before today
    close_5_ago = closes[-(RET_LOOKBACK + 1)]
    ret_5d = (close / close_5_ago - 1.0) if close_5_ago else 0.0

    # --- Stage 1: must pass ALL, else dropped ---
    if not (close > ma20 and close > ma60):
        return None
    if close < high20:  # 20-day closing high (today included -> close is the window max)
        return None
    if mean20_vol_before <= 0 or today_volume <= VOL_MULT_MIN * mean20_vol_before:
        return None
    if ret_5d >= RET_MAX:  # overheated hard-filter
        return None

    mean20_vol = _mean(volumes[-VOL_BASELINE:])
    span60 = high60 - low60
    price_pos_60d = ((close - low60) / span60 * 100.0) if span60 > 0 else 0.0

    return {
        "close": close,
        "ma20": ma20,
        "ma60": ma60,
        "high_20": high20,
        "high_60": high60,
        "low_60": low60,
        "today_volume": today_volume,
        "mean20_vol_before": mean20_vol_before,
        "mean20_vol": mean20_vol,
        "close_ma20": close / ma20 if ma20 else 0.0,
        "close_ma60": close / ma60 if ma60 else 0.0,
        "vol_mult": today_volume / mean20_vol_before if mean20_vol_before else 0.0,
        "price_pos_60d": price_pos_60d,
        "ret_5d": ret_5d,
        "is_60d_high": close >= high60,
        "crowded": price_pos_60d > CROWDED_THRESHOLD,
    }


def screen(panel: Panel, asof: str | None = None) -> list[Candidate]:
    """Stage-1 gate + cross-sectional score the TW universe as of ``asof``
    (default: the last panel row). Pure — no network, no DB."""
    close_df = panel.close
    if close_df.empty:
        return []
    asof = asof if asof is not None else str(close_df.index[-1])
    if asof not in close_df.index:
        return []
    pos = close_df.index.get_loc(asof)
    window_start = max(0, pos - MA_LONG + 1)
    window_dates = close_df.index[window_start : pos + 1]

    # Global degraded: no institutional feed at all (None) or a total-outage empty
    # frame (0 rows or 0 columns) -> no candidate gets an institution score.
    global_degraded = panel.institutional is None or panel.institutional.empty

    pool: list[dict] = []
    for ticker in close_df.columns:
        if not passes_universe(ticker):
            continue
        closes = close_df[ticker].reindex(window_dates)
        if closes.isna().any():  # any hole in the window -> not enough clean history
            continue
        if ticker not in panel.volume.columns:
            continue
        volumes = panel.volume[ticker].reindex(window_dates)
        if volumes.isna().any():  # any hole in the volume window -> baseline can't be trusted
            continue
        metrics = compute_stage1_metrics(list(window_dates), closes.tolist(), volumes.tolist())
        if metrics is None:
            continue

        ticker_degraded = global_degraded
        if not global_degraded:
            if ticker in panel.institutional.columns:
                # Missing DATES within the window fillna(0) correctly -> no reported flow that day.
                insti_sum = float(
                    panel.institutional[ticker]
                    .reindex(window_dates)
                    .fillna(0.0)
                    .tail(INSTITUTION_LOOKBACK)
                    .sum()
                )
                metrics["institution_raw"] = (
                    insti_sum / metrics["mean20_vol"] if metrics["mean20_vol"] > 0 else 0.0
                )
            else:
                # Ticker has no institutional column at all -> don't fabricate a value.
                ticker_degraded = True

        metrics["ticker"] = ticker
        metrics["degraded"] = ticker_degraded
        pool.append(metrics)

    if not pool:
        return []

    r_ma20 = pctrank([p["close_ma20"] - 1.0 for p in pool])
    r_ma60 = pctrank([p["close_ma60"] - 1.0 for p in pool])
    r_vol = pctrank([p["vol_mult"] for p in pool])

    # pctrank the institution factor over only the candidates that have it.
    insti_pool = [p for p in pool if "institution_raw" in p]
    r_inst_by_ticker = dict(
        zip((p["ticker"] for p in insti_pool), pctrank([p["institution_raw"] for p in insti_pool]))
    )

    candidates: list[Candidate] = []
    for idx, p in enumerate(pool):
        scores = {"momentum": (r_ma20[idx] + r_ma60[idx] + r_vol[idx]) / 3.0}
        if p["ticker"] in r_inst_by_ticker:
            scores["institution"] = r_inst_by_ticker[p["ticker"]]
        final = weighted_score(scores, WEIGHTS)
        factors = {k: p[k] for k in _FACTOR_KEYS if k in p}
        candidates.append(
            Candidate(
                ticker=p["ticker"],
                date=asof,
                rank=0,
                final_score=final,
                scores=scores,
                factors=factors,
                flags={
                    "is_60d_high": p["is_60d_high"],
                    "crowded": p["crowded"],
                    "degraded": p["degraded"],
                },
            )
        )

    # Rank 1 = highest final_score. Stable tie-break by ticker for determinism.
    candidates.sort(key=lambda c: (-c.final_score, c.ticker))
    for rank, c in enumerate(candidates, start=1):
        c.rank = rank
    return candidates
