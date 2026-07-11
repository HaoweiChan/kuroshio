"""US equity/options allocation defaults."""

from __future__ import annotations

from typing import Tuple

from kuroshio.agents.engine.payloads.schema import (
    InstrumentKind,
    RecommendedInstrument,
    RiskControls,
    Sizing,
)
from kuroshio.agents.engine.portfolio.state import PortfolioSnapshot


US_ALLOCATION_BY_RATING = {
    "Buy": 0.08,
    "Overweight": 0.05,
    "Hold": 0.0,
    "Underweight": -0.03,
    "Sell": -1.0,
}


def size_us_position(
    *,
    ticker: str,
    rating: str,
    latest_price: float | None,
    portfolio: PortfolioSnapshot,
) -> Tuple[RecommendedInstrument, Sizing, RiskControls]:
    allocation = US_ALLOCATION_BY_RATING.get(str(rating), 0.0)
    kind = InstrumentKind.CASH if allocation == 0 else InstrumentKind.STOCK
    instrument = RecommendedInstrument(
        kind=kind,
        symbol=ticker.upper() if kind != InstrumentKind.CASH else "USD",
        underlying=ticker.upper(),
        currency="USD",
        exchange="US",
        multiplier=1 if kind != InstrumentKind.CASH else None,
    )

    notional = None
    quantity = None
    if portfolio.nav is not None and allocation > 0:
        notional = portfolio.nav * allocation
        if latest_price and latest_price > 0:
            quantity = int(notional // latest_price)
    elif portfolio.nav is not None and allocation < 0:
        notional = portfolio.nav * allocation

    return (
        instrument,
        Sizing(
            action=str(rating),
            quantity=quantity,
            notional=notional,
            nav=portfolio.nav,
            nav_currency=portfolio.currency,
            allocation_pct_nav=allocation,
            cap_passed=not portfolio.stale,
            fallback_reason="stale_nav" if portfolio.stale else None,
        ),
        RiskControls(blocked_reason="stale_nav" if portfolio.stale else None),
    )

