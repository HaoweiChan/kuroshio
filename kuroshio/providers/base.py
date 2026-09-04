"""The provider contract (ARCHITECTURE.md rule 3: core logic never imports a data vendor).

Screening, scoring, and the allocator only ever see a `Panel`; every vendor-specific
detail — auth, rate limits, response shapes — stays behind this ABC so swapping or
adding a market data source never touches core logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from kuroshio.types import Panel


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_panel(self, tickers: list[str], lookback_days: int, end: str | None = None) -> Panel: ...

    def fetch_fundamentals(self, ticker: str) -> dict | None:
        """Optional. Most providers don't have a fundamentals feed wired up yet — yfinance does."""
        return None
