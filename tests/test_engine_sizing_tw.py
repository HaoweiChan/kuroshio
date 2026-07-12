"""Ported from the TradingAgents fork's tests/test_sizing_tw.py.

Account label genericized from a real broker name to "test-account".
"""

import pytest

from kuroshio.agents.engine.payloads.schema import InstrumentKind
from kuroshio.agents.engine.portfolio.sizing_tw import size_tw_position
from kuroshio.agents.engine.portfolio.state import AccountState, PortfolioSnapshot


def _snapshot(nav=1_000_000, existing_margin=0, stale=False):
    return PortfolioSnapshot(
        market="tw",
        currency="TWD",
        as_of="2026-06-17",
        nav=nav,
        stale=stale,
        accounts=[
            AccountState(
                account="test-account",
                currency="TWD",
                as_of="2026-06-17",
                nav=nav,
                source_path="/tmp/equity_history.json",
                metrics={"initial_margin": existing_margin},
            )
        ],
    )


def test_prefers_standard_ssf_when_margin_cap_fits():
    instrument, sizing, controls = size_tw_position(
        ticker="2330.TW",
        rating="Buy",
        latest_price=1000,
        futures_candidates=[
            {
                "symbol": "CDF",
                "underlying": "2330",
                "multiplier": 2000,
                "initial_margin_rate": 3.0,
                "margin_group": "Group1",
            },
            {"symbol": "QFF", "underlying": "2330", "multiplier": 100, "initial_margin": 5000},
        ],
        portfolio=_snapshot(nav=1_000_000),
        analyst_signals={"technical_momentum": True, "chip_momentum": True},
    )

    assert instrument.kind == InstrumentKind.SSF
    assert instrument.symbol == "CDF"
    assert instrument.multiplier == 2000
    assert sizing.initial_margin == 60_000
    assert sizing.initial_margin_pct_nav == pytest.approx(0.06)
    assert sizing.cap_passed is True
    assert controls.max_initial_margin_pct_nav == 0.075


def test_falls_back_to_mini_when_standard_breaches_cap():
    instrument, sizing, _ = size_tw_position(
        ticker="2330.TW",
        rating="Overweight",
        latest_price=1000,
        futures_candidates=[
            {"symbol": "CDF", "underlying": "2330", "multiplier": 2000, "initial_margin_rate": 13.5},
            {"symbol": "QFF", "underlying": "2330", "multiplier": 100, "initial_margin": 7000},
        ],
        portfolio=_snapshot(nav=1_000_000),
        analyst_signals={"technical_momentum": "strong breakout", "chip_momentum": "foreign net buy"},
    )

    assert instrument.kind == InstrumentKind.SSF
    assert instrument.symbol == "QFF"
    assert sizing.initial_margin == 7000
    assert sizing.details["rejected_candidates"][0]["reason"] == "margin_cap"


def test_falls_back_to_stock_when_no_futures_support():
    instrument, sizing, _ = size_tw_position(
        ticker="1234.TW",
        rating="Buy",
        latest_price=50,
        futures_candidates=[],
        portfolio=_snapshot(),
        analyst_signals={"technical_momentum": True, "chip_momentum": True},
    )

    assert instrument.kind == InstrumentKind.STOCK
    assert sizing.fallback_reason == "no_futures_support"


def test_blocks_futures_when_nav_is_stale():
    instrument, sizing, controls = size_tw_position(
        ticker="2330.TW",
        rating="Buy",
        latest_price=1000,
        futures_candidates=[
            {"symbol": "CDF", "underlying": "2330", "multiplier": 2000, "initial_margin": 50_000}
        ],
        portfolio=_snapshot(stale=True),
        analyst_signals={"technical_momentum": True, "chip_momentum": True},
    )

    assert instrument.kind == InstrumentKind.STOCK
    assert sizing.fallback_reason == "stale_nav"
    assert controls.blocked_reason == "stale_nav"


def test_aggregate_existing_margin_cap_is_enforced():
    instrument, sizing, _ = size_tw_position(
        ticker="2330.TW",
        rating="Buy",
        latest_price=1000,
        futures_candidates=[
            {"symbol": "QFF", "underlying": "2330", "multiplier": 100, "initial_margin": 20_000}
        ],
        portfolio=_snapshot(nav=1_000_000, existing_margin=70_000),
        analyst_signals={"technical_momentum": True, "chip_momentum": True},
    )

    assert instrument.kind == InstrumentKind.STOCK
    assert sizing.fallback_reason == "futures_margin_cap_breached"
