"""FinMind provider — TW OHLCV + 三大法人 (institutional) flow, the only market where
`Panel.institutional` is populated. Talks to the FinMind REST API v4 directly with
``requests`` (no SDK dependency for two endpoints). Works token-free at the free
tier's 600 req/hr; set ``FINMIND_TOKEN`` for a higher limit. Requests are sequential,
two per ticker (price + institutional) — polite by construction, no need for a
concurrency knob at this call volume.
"""

from __future__ import annotations

import os

import pandas as pd

from kuroshio.providers.base import MarketDataProvider
from kuroshio.types import Panel

BASE_URL = "https://api.finmindtrade.com/api/v4/data"
_INSTITUTIONAL_NAMES = ("Foreign_Investor", "Investment_Trust")


def _price_frames(records_by_ticker: dict[str, list[dict]]) -> tuple[pd.DataFrame, ...]:
    """TaiwanStockPrice records -> wide close/volume/high/low frames. Pure — no network.

    FinMind spells the session extremes ``max``/``min``. A ticker whose records omit a
    field is simply absent from that frame, rather than having one invented from close."""
    fields = ("close", "Trading_Volume", "max", "min")
    cols: dict[str, dict[str, pd.Series]] = {f: {} for f in fields}
    for ticker, records in records_by_ticker.items():
        if not records:
            continue
        df = pd.DataFrame(records).set_index("date")
        for f in fields:
            if f in df.columns:
                cols[f][ticker] = df[f]
    return tuple(pd.DataFrame(cols[f]).sort_index() for f in fields)


def _institutional_frame(records_by_ticker: dict[str, list[dict]]) -> pd.DataFrame:
    """TaiwanStockInstitutionalInvestorsBuySell records -> wide net-buy-shares frame.

    Net = buy - sell, summed over the foreign investor + investment trust rows
    (FinMind reports one buy/sell row per institutional-investor ``name`` per day).
    """
    cols = {}
    for ticker, records in records_by_ticker.items():
        if not records:
            continue
        df = pd.DataFrame(records)
        df = df[df["name"].isin(_INSTITUTIONAL_NAMES)]
        if df.empty:
            continue
        net = df["buy"] - df["sell"]
        cols[ticker] = net.groupby(df["date"]).sum()
    return pd.DataFrame(cols).sort_index()


def _shape_panel(
    price_by_ticker: dict[str, list[dict]], institutional_by_ticker: dict[str, list[dict]]
) -> Panel:
    close, volume, high, low = _price_frames(price_by_ticker)
    institutional = _institutional_frame(institutional_by_ticker)
    return Panel(close=close, volume=volume, institutional=institutional, high=high, low=low)


class FinMindProvider(MarketDataProvider):
    name = "finmind"

    def fetch_panel(self, tickers: list[str], lookback_days: int, end: str | None = None) -> Panel:
        end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
        start_ts = end_ts - pd.Timedelta(days=lookback_days)
        start, stop = start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d")

        price_by_ticker = {t: self._fetch("TaiwanStockPrice", t, start, stop) for t in tickers}
        institutional_by_ticker = {
            t: self._fetch("TaiwanStockInstitutionalInvestorsBuySell", t, start, stop) for t in tickers
        }
        return _shape_panel(price_by_ticker, institutional_by_ticker)

    def _fetch(self, dataset: str, ticker: str, start: str, stop: str) -> list[dict]:
        import requests  # lazy: keeps the module importable without the finmind extra

        params = {"dataset": dataset, "data_id": ticker, "start_date": start, "end_date": stop}
        token = os.getenv("FINMIND_TOKEN")
        if token:
            params["token"] = token
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("data", [])
