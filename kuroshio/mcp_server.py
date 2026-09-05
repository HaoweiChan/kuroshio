"""``kuroshio mcp`` — a stdio MCP server exposing the engine's dataflows (plus
``screen``/``propose``/``record_rating``) as tools for a Claude Code session.

TASK-10: ``kuroshio research`` costs 15-25 paid LLM calls per name. When the
owner asks a Claude Code session to research names instead, the reasoning runs
*in that session* (already paid for) and only the data comes from here — this
module never calls an LLM itself. To keep that true structurally (not just by
convention), it imports ONLY ``kuroshio.core.*``, ``kuroshio.providers``,
``kuroshio.core.screening``, and ``kuroshio.agents.engine.dataflows.*`` at
module scope; ``kuroshio.agents.engine.llm_clients`` and
``kuroshio.agents.engine.graph`` (the LLM/graph machinery) must never appear in
``sys.modules`` after :func:`build_server` runs — see ``tests/test_mcp_server.py``.

``screen``/``propose`` reuse ``kuroshio.cli``'s own helpers (imported lazily,
inside the tool bodies, to keep that module-scope import list honest) so a
session's read path is the exact same code ``kuroshio screen``/``kuroshio
propose`` run — not a reimplementation that could drift from it.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from kuroshio.agents.engine.dataflows.interface import route_to_vendor
from kuroshio.core import ledger
from kuroshio.core.screening import get_profile

# Matches ledger._HIT_RULES' vocabulary — the five-tier rating scale every
# analyst-facing role in the engine (research manager, portfolio manager) uses.
_VALID_RATINGS = {"buy", "overweight", "hold", "underweight", "sell"}


def build_server() -> MCPServer:
    server = MCPServer(name="kuroshio")

    # --- data tools: thin wrappers over route_to_vendor, same param names the
    # engine's own @tool wrappers use (kuroshio/agents/engine/agents/utils/*_tools.py) ---

    @server.tool()
    def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
        """OHLCV price history for a ticker between two dates (yyyy-mm-dd)."""
        return route_to_vendor("get_stock_data", symbol, start_date, end_date)

    @server.tool()
    def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
        """A technical indicator (e.g. 'rsi', 'macd', 'close_50_sma') for a ticker over a
        trailing window ending at curr_date (yyyy-mm-dd)."""
        return route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)

    @server.tool()
    def get_fundamentals(ticker: str, curr_date: str) -> str:
        """Company fundamentals overview: valuation, margins, balance-sheet ratios."""
        return route_to_vendor("get_fundamentals", ticker, curr_date)

    @server.tool()
    def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
        """Balance sheet statement ('annual' or 'quarterly')."""
        return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)

    @server.tool()
    def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
        """Cash flow statement ('annual' or 'quarterly')."""
        return route_to_vendor("get_cashflow", ticker, freq, curr_date)

    @server.tool()
    def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
        """Income statement ('annual' or 'quarterly')."""
        return route_to_vendor("get_income_statement", ticker, freq, curr_date)

    @server.tool()
    def get_analyst_estimates(ticker: str, curr_date: str) -> str:
        """Analyst estimate revisions, earnings estimates, recommendation trend, and the
        next earnings date."""
        return route_to_vendor("get_analyst_estimates", ticker, curr_date)

    @server.tool()
    def get_insider_transactions(ticker: str) -> str:
        """Insider buy/sell transactions."""
        return route_to_vendor("get_insider_transactions", ticker)

    @server.tool()
    def get_news(ticker: str, start_date: str, end_date: str) -> str:
        """Ticker-specific news between two dates (yyyy-mm-dd)."""
        return route_to_vendor("get_news", ticker, start_date, end_date)

    @server.tool()
    def get_global_news(
        curr_date: str, look_back_days: int | None = None, limit: int | None = None
    ) -> str:
        """Broader macro/world-affairs news; omit look_back_days/limit for the engine's
        configured defaults."""
        return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

    @server.tool()
    def get_macro_indicators(
        indicator: str, curr_date: str, look_back_days: int | None = None
    ) -> str:
        """A FRED macro series — a friendly alias ('cpi', 'fed_funds_rate', '10y_treasury',
        'unemployment', 'yield_curve', 'real_gdp', 'vix', ...) or a raw FRED series ID.
        Degrades to a DATA_UNAVAILABLE sentinel (not an error) without FRED_API_KEY set."""
        return route_to_vendor("get_macro_indicators", indicator, curr_date, look_back_days)

    # --- read-only tools over the allocator's own screen/propose code paths ---

    @server.tool()
    def screen(market: str, tickers: str, asof: str | None = None, top: int = 20) -> str:
        """Rank breakout candidates in `market` (the same gate `kuroshio screen` runs).
        `tickers` is a comma-separated list, or a path to a newline-separated file or a
        `date,tickers` snapshot (scripts/sp500_members.py). Returns a JSON list of rows
        (ticker/rank/final_score/scores/factors/flags)."""
        from kuroshio.cli import _candidate_to_dict, _load_universe, _parse_tickers
        from kuroshio.providers import get_provider

        profile = get_profile(market)
        try:
            names = _load_universe(tickers) if Path(tickers).exists() else _parse_tickers(tickers, None)
        except ValueError as exc:
            return f"error: {exc}"
        if not names:
            return "error: tickers resolved to zero names"

        # benchmark first: providers/yf.py:_shape_panel filters the panel to its first
        # resolved ticker, so a delisted name in that slot would truncate the whole panel.
        fetch_tickers = [profile.benchmark] if profile.benchmark else []
        fetch_tickers += [t for t in names if t not in fetch_tickers]

        try:
            provider = get_provider(profile.default_provider)
            panel = provider.fetch_panel(fetch_tickers, profile.lookback_days, end=asof)
        except ImportError as exc:
            return f"error: {exc}"

        candidates = profile.screen(panel, asof=asof)
        return json.dumps([_candidate_to_dict(c) for c in candidates[:top]])

    @server.tool()
    def propose(
        ips_path: str, holdings_path: str, market: str, universe_file: str | None = None
    ) -> str:
        """Propose portfolio swaps against an IPS (the same path `kuroshio propose` runs,
        minus --candidates/--discord-webhook). Returns the proposal cards' markdown, or
        "No proposals"."""
        from kuroshio.cli import _run_propose

        cards, problems = _run_propose(ips_path, holdings_path, market, universe_file=universe_file)
        if problems is not None:
            return "\n".join(problems)
        if not cards:
            return "No proposals"
        return "\n\n".join(card.to_markdown() for card in cards)

    # --- the one write tool ---

    @server.tool()
    def record_rating(
        ticker: str,
        date: str,
        rating: str,
        stop_loss: float | None = None,
        price_target: float | None = None,
        close: float | None = None,
        source: str = "claude-session",
        model: str | None = None,
        market: str = "us",
    ) -> str:
        """Append a rating row to the same ratings ledger `kuroshio research` writes to
        (read back by `kuroshio evaluate`). `rating` must be one of
        Buy/Overweight/Hold/Underweight/Sell (case-insensitive); anything else is
        rejected with an error string and no row is written. `model` should name the
        tier that made the decision (e.g. the session's own model id) so `evaluate`
        can compare hit rates across sources/tiers."""
        if rating.strip().lower() not in _VALID_RATINGS:
            return (
                f"error: rating {rating!r} is not one of "
                "Buy/Overweight/Hold/Underweight/Sell"
            )
        row = {
            "date": date, "market": market, "ticker": ticker, "rating": rating,
            "stop_loss": stop_loss, "price_target": price_target, "close": close,
            "source": source, "model": model,
        }
        path = ledger.ledger_dir() / ledger.RATINGS
        ledger.append(path, [row])
        return str(path)

    return server


def run() -> None:
    build_server().run()
