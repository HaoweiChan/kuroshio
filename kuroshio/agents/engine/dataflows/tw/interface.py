"""Tool-facing Taiwan dataflow interface."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import finmind, taifex


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    return finmind.get_stock_data(symbol, start_date, end_date)


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
    return finmind.get_indicators(symbol, indicator, curr_date, look_back_days)


def get_fundamentals(symbol: str, curr_date: str = None) -> str:
    return finmind.get_fundamentals(symbol, curr_date)


def get_balance_sheet(symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return finmind.get_balance_sheet(symbol, curr_date)


def get_cashflow(symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return finmind.get_cashflow(symbol, curr_date)


def get_income_statement(symbol: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return finmind.get_income_statement(symbol, curr_date)


def get_news(symbol: str, start_date: str, end_date: str) -> str:
    return finmind.get_news(symbol, start_date, end_date)


def get_global_news(curr_date: str = None, lookback_days: int = 7, limit: int = None) -> str:
    return finmind.get_global_news(curr_date or datetime.now().strftime("%Y-%m-%d"), lookback_days)


def get_insider_transactions(symbol: str, start_date: str = None, end_date: str = None) -> str:
    if end_date is None:
        end = datetime.now()
        end_date = end.strftime("%Y-%m-%d")
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    if start_date is None:
        start_date = (end - timedelta(days=365)).strftime("%Y-%m-%d")
    return finmind.get_insider_transactions(symbol, start_date, end_date)


def get_institutional_flow(symbol: str, curr_date: str, look_back_days: int = 20) -> str:
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = (end - timedelta(days=look_back_days * 2)).strftime("%Y-%m-%d")
    return finmind.get_institutional_flow(symbol, start, curr_date)


def get_margin_flow(symbol: str, curr_date: str, look_back_days: int = 20) -> str:
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = (end - timedelta(days=look_back_days * 2)).strftime("%Y-%m-%d")
    return finmind.get_margin_flow(symbol, start, curr_date)


def get_futures_candidates(symbol: str) -> str:
    return taifex.format_ssf_candidates(symbol)
