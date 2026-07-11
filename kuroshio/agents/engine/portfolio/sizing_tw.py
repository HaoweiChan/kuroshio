"""Taiwan portfolio sizing with SSF margin guardrails."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

from kuroshio.agents.engine.payloads.schema import (
    InstrumentKind,
    RecommendedInstrument,
    RiskControls,
    Sizing,
)
from kuroshio.agents.engine.portfolio.state import PortfolioSnapshot


TW_INITIAL_MARGIN_NAV_CAP = 0.075
STANDARD_STOCK_SSF_MULTIPLIER = 2000
MINI_STOCK_SSF_MULTIPLIER = 100
_FUTURES_RATINGS = {"Buy", "Overweight"}


def normalize_tw_ticker(ticker: str) -> str:
    upper = ticker.upper().strip()
    for suffix in (".TW", ".TWO"):
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper


def _truthy_signal(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        text = value.lower()
        return any(
            token in text
            for token in (
                "high",
                "strong",
                "bullish",
                "positive",
                "breakout",
                "net buy",
                "accumulation",
                "momentum",
            )
        )
    return False


def has_high_tw_momentum(signals: Dict[str, Any]) -> bool:
    return _truthy_signal(signals.get("technical_momentum")) and _truthy_signal(
        signals.get("chip_momentum")
    )


def _candidate_multiplier(candidate: Dict[str, Any]) -> Optional[int]:
    value = candidate.get("multiplier")
    if value is None:
        value = candidate.get("contract_multiplier")
    return int(value) if value is not None else None


def _candidate_initial_margin(
    candidate: Dict[str, Any],
    price: Optional[float],
) -> Optional[float]:
    direct = candidate.get("initial_margin")
    if direct is not None:
        return float(direct)

    rate = candidate.get("initial_margin_rate")
    multiplier = _candidate_multiplier(candidate)
    if rate is None or multiplier is None or price is None:
        return None
    rate_float = float(rate)
    if rate_float > 1:
        rate_float /= 100
    return float(price) * multiplier * rate_float


def _sort_candidates(candidates: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    def key(candidate: Dict[str, Any]) -> Tuple[int, str]:
        multiplier = _candidate_multiplier(candidate) or 0
        priority = 0 if multiplier == STANDARD_STOCK_SSF_MULTIPLIER else 1
        if multiplier == MINI_STOCK_SSF_MULTIPLIER:
            priority = 2
        return priority, str(candidate.get("symbol") or candidate.get("ticker_symbol") or "")

    return sorted(candidates, key=key)


def _stock_instrument(ticker: str) -> RecommendedInstrument:
    underlying = normalize_tw_ticker(ticker)
    return RecommendedInstrument(
        kind=InstrumentKind.STOCK,
        symbol=f"{underlying}.TW",
        underlying=underlying,
        currency="TWD",
        exchange="TWSE",
        multiplier=1,
    )


def _cash_instrument(ticker: str) -> RecommendedInstrument:
    underlying = normalize_tw_ticker(ticker)
    return RecommendedInstrument(
        kind=InstrumentKind.CASH,
        symbol="TWD",
        underlying=underlying,
        currency="TWD",
        exchange="TW",
    )


def size_tw_position(
    *,
    ticker: str,
    rating: str,
    latest_price: Optional[float],
    futures_candidates: Iterable[Dict[str, Any]],
    portfolio: PortfolioSnapshot,
    analyst_signals: Optional[Dict[str, Any]] = None,
    nav_cap: float = TW_INITIAL_MARGIN_NAV_CAP,
) -> Tuple[RecommendedInstrument, Sizing, RiskControls]:
    """Choose stock shares or SSF for a TW recommendation.

    The function is deliberately conservative: absent fresh NAV, usable futures
    metadata, or both technical and chip momentum, it falls back to stock/cash.
    """
    signals = analyst_signals or {}
    rating_value = str(rating)
    nav = portfolio.nav
    existing_margin = portfolio.existing_initial_margin
    cap_amount = nav * nav_cap if nav is not None else None

    if rating_value not in _FUTURES_RATINGS:
        instrument = _cash_instrument(ticker) if rating_value in {"Sell", "Underweight"} else _stock_instrument(ticker)
        return (
            instrument,
            Sizing(
                action=rating_value,
                nav=nav,
                nav_currency=portfolio.currency,
                cap_passed=True,
                fallback_reason="rating_not_new_long_risk",
            ),
            RiskControls(max_initial_margin_pct_nav=nav_cap),
        )

    if nav is None or nav <= 0:
        return (
            _stock_instrument(ticker),
            Sizing(
                action=rating_value,
                nav=nav,
                nav_currency=portfolio.currency,
                cap_passed=False,
                fallback_reason="missing_nav",
            ),
            RiskControls(
                max_initial_margin_pct_nav=nav_cap,
                blocked_reason="missing_nav",
            ),
        )

    if portfolio.stale:
        return (
            _stock_instrument(ticker),
            Sizing(
                action=rating_value,
                nav=nav,
                nav_currency=portfolio.currency,
                cap_passed=False,
                fallback_reason="stale_nav",
            ),
            RiskControls(
                max_initial_margin_pct_nav=nav_cap,
                blocked_reason="stale_nav",
            ),
        )

    if not has_high_tw_momentum(signals):
        return (
            _stock_instrument(ticker),
            Sizing(
                action=rating_value,
                nav=nav,
                nav_currency=portfolio.currency,
                cap_passed=True,
                fallback_reason="momentum_threshold_not_met",
            ),
            RiskControls(max_initial_margin_pct_nav=nav_cap),
        )

    candidates = _sort_candidates(futures_candidates)
    if not candidates:
        return (
            _stock_instrument(ticker),
            Sizing(
                action=rating_value,
                nav=nav,
                nav_currency=portfolio.currency,
                cap_passed=True,
                fallback_reason="no_futures_support",
            ),
            RiskControls(max_initial_margin_pct_nav=nav_cap),
        )

    rejected: list[Dict[str, Any]] = []
    for candidate in candidates:
        multiplier = _candidate_multiplier(candidate)
        if multiplier not in (STANDARD_STOCK_SSF_MULTIPLIER, MINI_STOCK_SSF_MULTIPLIER):
            continue
        initial_margin = _candidate_initial_margin(candidate, latest_price)
        if initial_margin is None:
            rejected.append({"symbol": candidate.get("symbol"), "reason": "missing_margin"})
            continue
        post_trade = (existing_margin or 0.0) + initial_margin
        single_ok = cap_amount is not None and initial_margin <= cap_amount
        aggregate_ok = cap_amount is not None and post_trade <= cap_amount
        if single_ok and aggregate_ok:
            underlying = normalize_tw_ticker(ticker)
            symbol = str(candidate.get("symbol") or candidate.get("ticker_symbol"))
            instrument = RecommendedInstrument(
                kind=InstrumentKind.SSF,
                symbol=symbol,
                underlying=underlying,
                currency="TWD",
                exchange="TAIFEX",
                multiplier=multiplier,
                contract_month=candidate.get("contract_month"),
                metadata={
                    "margin_group": candidate.get("margin_group"),
                    "underlying_name": candidate.get("underlying_name"),
                },
            )
            sizing = Sizing(
                action=rating_value,
                quantity=1,
                notional=(latest_price * multiplier) if latest_price is not None else None,
                nav=nav,
                nav_currency=portfolio.currency,
                allocation_pct_nav=(
                    latest_price * multiplier / nav
                    if latest_price is not None and nav
                    else None
                ),
                initial_margin=initial_margin,
                initial_margin_pct_nav=initial_margin / nav,
                post_trade_initial_margin=post_trade,
                cap_passed=True,
                margin_group=candidate.get("margin_group"),
                details={"rejected_candidates": rejected},
            )
            return (
                instrument,
                sizing,
                RiskControls(max_initial_margin_pct_nav=nav_cap),
            )
        rejected.append(
            {
                "symbol": candidate.get("symbol"),
                "reason": "margin_cap",
                "initial_margin": initial_margin,
                "post_trade_initial_margin": post_trade,
            }
        )

    return (
        _stock_instrument(ticker),
        Sizing(
            action=rating_value,
            nav=nav,
            nav_currency=portfolio.currency,
            cap_passed=False,
            fallback_reason="futures_margin_cap_breached",
            details={"rejected_candidates": rejected},
        ),
        RiskControls(max_initial_margin_pct_nav=nav_cap),
    )

