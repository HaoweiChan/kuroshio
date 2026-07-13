"""FinMind-backed Taiwan market data helpers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, Iterable, Optional
from urllib.parse import urlsplit

import pandas as pd
import requests


FINMIND_BASE_URL = os.getenv("FINMIND_BASE_URL", "https://api.finmindtrade.com/api/v4/data")
TINBOKER_WIKI_URL = os.getenv("TINBOKER_WIKI_URL", "https://podcast-api.tinboker.com")
_WIKI_NEWS_TOKEN_BUDGET = 1500


def normalize_tw_symbol(symbol: str) -> str:
    upper = symbol.upper().strip()
    for suffix in (".TW", ".TWO"):
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper


def _request_dataset(dataset: str, **params) -> pd.DataFrame:
    payload = {"dataset": dataset, **{k: v for k, v in params.items() if v is not None}}
    token = os.getenv("FINMIND_TOKEN")
    if token:
        payload["token"] = token
    response = requests.get(FINMIND_BASE_URL, params=payload, timeout=20)
    response.raise_for_status()
    body = response.json()
    data = body.get("data", [])
    return pd.DataFrame(data)


def _format_df(df: pd.DataFrame, title: str) -> str:
    if df.empty:
        return f"# {title}\nNo data found."
    csv = df.to_csv(index=False)
    return (
        f"# {title}\n"
        f"# Total records: {len(df)}\n"
        f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{csv}"
    )


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    stock_id = normalize_tw_symbol(symbol)
    df = _request_dataset(
        "TaiwanStockPrice",
        data_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )
    columns = [
        col
        for col in ("date", "stock_id", "Trading_Volume", "open", "max", "min", "close")
        if col in df.columns
    ]
    return _format_df(df[columns] if columns else df, f"FinMind TaiwanStockPrice {stock_id}")


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Compute simple stockstats-style indicators from FinMind OHLCV data."""
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = (end - relativedelta(days=max(look_back_days * 3, 60))).strftime("%Y-%m-%d")
    raw = _request_dataset(
        "TaiwanStockPrice",
        data_id=normalize_tw_symbol(symbol),
        start_date=start,
        end_date=curr_date,
    )
    if raw.empty:
        return f"No price data found for {symbol} before {curr_date}"

    data = raw.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "max": "High",
            "min": "Low",
            "close": "Close",
            "Trading_Volume": "Volume",
        }
    )
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        return f"FinMind data missing columns for indicators: {', '.join(missing)}"
    df = wrap(data[required].copy())
    ind = indicator.strip().lower()
    df[ind]
    out = df[["Date", ind]].tail(look_back_days)
    return _format_df(out, f"{ind} values for {normalize_tw_symbol(symbol)}")


def get_fundamentals(symbol: str, curr_date: Optional[str] = None) -> str:
    stock_id = normalize_tw_symbol(symbol)
    date_str = curr_date or datetime.now().strftime("%Y-%m-%d")
    frames = []
    for dataset in ("TaiwanStockPER", "TaiwanStockMonthRevenue", "TaiwanStockMarketValue"):
        try:
            df = _request_dataset(dataset, data_id=stock_id, start_date=date_str[:7] + "-01")
            if not df.empty:
                df.insert(0, "dataset", dataset)
                frames.append(df.tail(12))
        except Exception as exc:
            frames.append(pd.DataFrame([{"dataset": dataset, "error": str(exc)}]))
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return _format_df(merged, f"FinMind fundamentals {stock_id}")


def get_balance_sheet(symbol: str, curr_date: Optional[str] = None) -> str:
    return _statement("TaiwanStockBalanceSheet", symbol, curr_date)


def get_cashflow(symbol: str, curr_date: Optional[str] = None) -> str:
    return _statement("TaiwanStockCashFlowsStatement", symbol, curr_date)


def get_income_statement(symbol: str, curr_date: Optional[str] = None) -> str:
    return _statement("TaiwanStockFinancialStatements", symbol, curr_date)


def _statement(dataset: str, symbol: str, curr_date: Optional[str]) -> str:
    date_str = curr_date or datetime.now().strftime("%Y-%m-%d")
    start = f"{int(date_str[:4]) - 2}-01-01"
    df = _request_dataset(dataset, data_id=normalize_tw_symbol(symbol), start_date=start)
    return _format_df(df.tail(80), f"FinMind {dataset} {normalize_tw_symbol(symbol)}")


def get_institutional_flow(symbol: str, start_date: str, end_date: str) -> str:
    stock_id = normalize_tw_symbol(symbol)
    df = _request_dataset(
        "TaiwanStockInstitutionalInvestorsBuySell",
        data_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )
    return _format_df(df, f"FinMind institutional flow {stock_id}")


def get_margin_flow(symbol: str, start_date: str, end_date: str) -> str:
    stock_id = normalize_tw_symbol(symbol)
    df = _request_dataset(
        "TaiwanStockMarginPurchaseShortSale",
        data_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )
    return _format_df(df, f"FinMind margin/short flow {stock_id}")


def _wiki_get(path: str, **params) -> Optional[dict]:
    """GET a tinboker wiki endpoint. Returns None on a 404 (no coverage —
    treated as "no news", not an error). Raises on other HTTP/network errors
    so callers can degrade with a specific message instead of silently.
    """
    response = requests.get(f"{TINBOKER_WIKI_URL}{path}", params=params, timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _wiki_source_label(excerpt: dict) -> str:
    host = urlsplit(excerpt.get("source_url") or "").netloc
    return host or excerpt.get("page_kind", "unknown")


def get_news(symbol: str, start_date: str, end_date: str) -> str:
    code = normalize_tw_symbol(symbol)
    title = f"# Taiwan news & sentiment for {code}"
    try:
        data = _wiki_get("/api/wiki/context", topic=code, tokens=_WIKI_NEWS_TOKEN_BUDGET)
    except requests.RequestException as exc:
        return f"{title}\nTinboker wiki lookup failed ({exc}); proceeding without TW news context."

    excerpts = (data or {}).get("excerpts", [])
    if not excerpts:
        return f"{title}\nNo recent Taiwan news found for {code}."

    in_window = [e for e in excerpts if start_date <= (e.get("date") or "") <= end_date]
    lines = [title]
    for excerpt in in_window or excerpts:
        lines.append(
            f"- [{excerpt.get('date', '?')}] ({_wiki_source_label(excerpt)}) "
            f"{(excerpt.get('text') or '').strip()} ({excerpt.get('source_url', '')})"
        )
    return "\n".join(lines)


def get_global_news(curr_date: str, lookback_days: int = 7) -> str:
    title = "# Taiwan / global market news"
    try:
        end = datetime.strptime(curr_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        end = datetime.now()
    date_from = (end - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    try:
        data = _wiki_get("/api/wiki/news", limit=20, date_from=date_from)
    except requests.RequestException as exc:
        return f"{title}\nTinboker wiki news lookup failed ({exc}); proceeding without TW/global news."

    articles = (data or {}).get("articles", [])
    if not articles:
        return f"{title}\nNo recent Taiwan/global news found."

    lines = [title]
    for article in articles:
        tickers = ", ".join(article.get("tickers") or [])
        lines.append(
            f"- [{article.get('date', '?')}] {article.get('title', '')} "
            f"— {article.get('source', '')} (tickers: {tickers}) {article.get('url', '')}"
        )
    return "\n".join(lines)


def get_insider_transactions(symbol: str, start_date: str, end_date: str) -> str:
    stock_id = normalize_tw_symbol(symbol)
    df = _request_dataset(
        "TaiwanStockShareholding",
        data_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )
    return _format_df(df, f"FinMind shareholding {stock_id}")


def _bulk_latest_rows(date: str, lookback_days: int = 10) -> pd.DataFrame:
    """One bulk market-wide TaiwanStockPrice call over a trailing window.

    Returns the most recent row per ``stock_id`` on or before ``date``. Using a
    window (not a single day) means the call still returns data when ``date``
    itself has not traded yet — e.g. a pre-open or weekend allocation run.
    Empty DataFrame on failure or unsupported bulk query.
    """
    from datetime import datetime as _dt, timedelta as _td

    try:
        start = (_dt.strptime(date, "%Y-%m-%d") - _td(days=max(lookback_days, 5))).strftime("%Y-%m-%d")
        df = _request_dataset("TaiwanStockPrice", start_date=start, end_date=date)
    except Exception:
        return pd.DataFrame()
    if df.empty or "stock_id" not in df.columns or "date" not in df.columns:
        return pd.DataFrame()
    return df.sort_values("date").groupby("stock_id", as_index=False).tail(1)


def latest_dollar_volume_all(date: str) -> Dict[str, float]:
    """Market-wide ``{stock_id: close * volume}`` from the latest available bar.

    Used for liquidity ranking; empty dict degrades the ranking to code order.
    """
    df = _bulk_latest_rows(date)
    if df.empty:
        return {}
    volumes: Dict[str, float] = {}
    for _, row in df.iterrows():
        try:
            close = float(row.get("close") or 0)
            volume = float(row.get("Trading_Volume") or 0)
        except (TypeError, ValueError):
            continue
        if close and volume:
            volumes[str(row["stock_id"])] = close * volume
    return volumes


def latest_close_all(date: str) -> Dict[str, float]:
    """Market-wide ``{stock_id: close}`` from the latest available bar."""
    df = _bulk_latest_rows(date)
    if df.empty or "close" not in df.columns:
        return {}
    closes: Dict[str, float] = {}
    for _, row in df.iterrows():
        try:
            close = float(row.get("close") or 0)
        except (TypeError, ValueError):
            continue
        if close:
            closes[str(row["stock_id"])] = close
    return closes


def load_csv_string(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(csv_text))

