from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import tw, us
from .score import pctrank

__all__ = ["tw", "us", "pctrank", "MarketProfile", "PROFILES", "get_profile"]


@dataclass(frozen=True)
class MarketProfile:
    """Everything the CLI needs to run a market end-to-end, without hardcoding
    per-market branches. Adding a market = one entry here (see docs/adding-a-market.md)."""

    name: str                      # registry key, e.g. "us"
    screen: Callable               # screen(panel, asof=None, **profile_options)
    # ungated incumbent scoring: score_names(panel, tickers, asof=None, **profile_options)
    score_names: Callable
    default_provider: str          # kuroshio.providers registry name
    lookback_days: int             # single-screen fetch window (calendar days)
    warmup_days: int               # backtest indicator warmup headroom (calendar days)
    min_history: int               # backtest first-rebalance row (trading sessions)
    benchmark: str | None          # reference ticker auto-added to fetches (None = none)
    # largest share of `final_score` one pctrank can control — see tw.MIN_RANK_WEIGHT
    min_rank_weight: float
    accepts_sector_map: bool = False


PROFILES = {
    # US MA200 needs ~200 trading sessions -> 320 calendar days single-screen lookback,
    # + weeks*7 -> 420 calendar days of backtest warmup headroom; first rebalance
    # row after 210 trading sessions.
    "us": MarketProfile(
        "us", us.screen, us.score_names, "yfinance", 320, 420, 210, "SPY",
        min_rank_weight=us.MIN_RANK_WEIGHT, accepts_sector_map=True,
    ),
    # TW MA60 needs ~60 trading sessions -> 120 calendar days single-screen lookback,
    # + weeks*7 -> 200 calendar days of backtest warmup headroom; first rebalance
    # row after 65 trading sessions. No institutional-flow benchmark ticker.
    "tw": MarketProfile(
        "tw", tw.screen, tw.score_names, "finmind", 120, 200, 65, None,
        min_rank_weight=tw.MIN_RANK_WEIGHT,
    ),
}


def get_profile(name: str) -> MarketProfile:
    if name not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown market {name!r}; known markets: {known}")
    return PROFILES[name]
