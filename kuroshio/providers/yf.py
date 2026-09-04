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


def _eps_revisions_fields(table) -> tuple[int | None, int | None]:
    """(eps_rev_up_30d, eps_rev_down_30d) off the '0y' (current fiscal year) row of
    ``Ticker.eps_revisions``. None/None when the table is missing, empty, or has
    no '0y' row."""
    if table is None or getattr(table, "empty", True) or "0y" not in table.index:
        return None, None
    row = table.loc["0y"]
    up, down = row.get("upLast30days"), row.get("downLast30days")
    return (
        None if pd.isna(up) else int(up),
        None if pd.isna(down) else int(down),
    )


def _earnings_estimate_fields(table) -> tuple[float | None, int | None]:
    """(eps_est_growth_fy, n_analysts) off the '0y' row of ``Ticker.earnings_estimate``."""
    if table is None or getattr(table, "empty", True) or "0y" not in table.index:
        return None, None
    row = table.loc["0y"]
    growth, n = row.get("growth"), row.get("numberOfAnalysts")
    return (
        None if pd.isna(growth) else float(growth),
        None if pd.isna(n) else int(n),
    )


def _recommendations_fields(table) -> tuple[int | None, int | None, int | None]:
    """(rec_buy, rec_hold, rec_sell) off the current-month ('0m') row of
    ``Ticker.recommendations_summary``. buy = strongBuy + buy, sell = sell + strongSell."""
    if table is None or getattr(table, "empty", True) or "period" not in table.columns:
        return None, None, None
    match = table[table["period"] == "0m"]
    if match.empty:
        return None, None, None
    row = match.iloc[0]
    strong_buy, buy, hold = row.get("strongBuy", 0), row.get("buy", 0), row.get("hold", 0)
    sell, strong_sell = row.get("sell", 0), row.get("strongSell", 0)
    if any(pd.isna(v) for v in (strong_buy, buy, hold, sell, strong_sell)):
        return None, None, None
    return int(strong_buy + buy), int(hold), int(sell + strong_sell)


def _next_earnings_date(calendar) -> str | None:
    """First entry of ``Ticker.calendar["Earnings Date"]`` as an ISO date string."""
    if not calendar:
        return None
    dates = calendar.get("Earnings Date")
    if not dates:
        return None
    d = dates[0]
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _last_surprise_pct(table) -> float | None:
    """Surprise(%) of the most recent ``Ticker.earnings_dates`` row with a reported
    EPS (future rows have NaN Reported EPS and are skipped)."""
    if table is None or getattr(table, "empty", True) or "Reported EPS" not in table.columns:
        return None
    reported = table.dropna(subset=["Reported EPS"]).sort_index()
    if reported.empty:
        return None
    val = reported.iloc[-1].get("Surprise(%)")
    return None if pd.isna(val) else float(val)


def _insider_net_shares_90d(table, today: pd.Timestamp | None = None) -> int | None:
    """Purchases minus sales (by ``Shares``) over ``Ticker.insider_transactions`` rows
    whose Start Date falls in the last 90 days. None if the table is missing; 0 if
    present but no row qualifies."""
    if table is None or getattr(table, "empty", True):
        return None
    if not {"Start Date", "Text", "Shares"} <= set(table.columns):
        return None
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=90)
    start = pd.to_datetime(table["Start Date"], errors="coerce")
    recent = table[(start >= cutoff) & (start <= today)]
    text = recent["Text"].astype(str)
    purchases = recent.loc[text.str.startswith("Purchase"), "Shares"].sum()
    sales = recent.loc[text.str.startswith("Sale"), "Shares"].sum()
    return int(purchases - sales)


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

    def fetch_fundamentals(self, ticker: str) -> dict | None:
        import yfinance as yf

        t = yf.Ticker(ticker)
        try:
            info = t.info
        except Exception:
            return None
        if not info:
            return None

        def _prop(name: str):
            # Each table is its own HTTP call; one failing/rate-limited table must
            # not blank out the others, so each is fetched (and caught) separately.
            try:
                return getattr(t, name)
            except Exception:
                return None

        eps_rev_up_30d, eps_rev_down_30d = _eps_revisions_fields(_prop("eps_revisions"))
        eps_est_growth_fy, n_analysts = _earnings_estimate_fields(_prop("earnings_estimate"))
        rec_buy, rec_hold, rec_sell = _recommendations_fields(_prop("recommendations_summary"))

        return {
            "forward_pe": info.get("forwardPE"),
            "forward_eps": info.get("forwardEps"),
            "trailing_eps": info.get("trailingEps"),
            "trailing_pe": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "eps_rev_up_30d": eps_rev_up_30d,
            "eps_rev_down_30d": eps_rev_down_30d,
            "eps_est_growth_fy": eps_est_growth_fy,
            "n_analysts": n_analysts,
            "rec_buy": rec_buy,
            "rec_hold": rec_hold,
            "rec_sell": rec_sell,
            "next_earnings_date": _next_earnings_date(_prop("calendar")),
            "last_surprise_pct": _last_surprise_pct(_prop("earnings_dates")),
            "insider_net_shares_90d": _insider_net_shares_90d(_prop("insider_transactions")),
        }
