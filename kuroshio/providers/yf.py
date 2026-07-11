"""yfinance provider — the zero-key default (ARCHITECTURE.md: "must work with zero API keys").

Module named ``yf`` (not ``yfinance``) so it doesn't shadow the real package on import.
yfinance itself is imported inside the fetch method, not at module scope, so
``kuroshio.providers.yf`` — and the pure shaping function tests exercise — stays
importable even when the yfinance extra isn't installed.
"""

from __future__ import annotations

import pandas as pd

from kuroshio.providers.base import MarketDataProvider
from kuroshio.types import Panel


def _iso_index(index: pd.Index) -> pd.Index:
    if isinstance(index, pd.DatetimeIndex):
        return index.strftime("%Y-%m-%d")
    return index.astype(str)


def _shape_panel(raw_close: pd.DataFrame, raw_volume: pd.DataFrame, tickers: list[str]) -> Panel:
    """Turn a raw yf.download() close/volume pair into a Panel. Pure — no network."""
    close = raw_close.dropna(axis=1, how="all")  # unresolved tickers -> all-NaN column
    volume = raw_volume.reindex(columns=close.columns)

    ref = next((t for t in tickers if t in close.columns), None)
    if ref is not None:
        keep = close[ref].notna()  # still-forming partial bar for the reference ticker
        close, volume = close.loc[keep], volume.loc[keep]

    close = close.sort_index()
    volume = volume.reindex(close.index)
    close.index = _iso_index(close.index)
    volume.index = _iso_index(volume.index)
    return Panel(close=close, volume=volume, institutional=None)


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def fetch_panel(self, tickers: list[str], lookback_days: int, end: str | None = None) -> Panel:
        import yfinance as yf

        end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
        start_ts = end_ts - pd.Timedelta(days=lookback_days)
        raw = yf.download(
            tickers,
            start=start_ts,
            end=end_ts + pd.Timedelta(days=1),
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        close, volume = raw["Close"], raw["Volume"]
        if isinstance(close, pd.Series):  # single ticker: no ticker level in the columns
            close, volume = close.to_frame(tickers[0]), volume.to_frame(tickers[0])
        return _shape_panel(close, volume, tickers)
