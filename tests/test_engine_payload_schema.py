"""Ported from the TradingAgents fork's tests/test_payload_schema.py."""

from kuroshio.agents.engine.payloads.schema import (
    InstrumentKind,
    MarketRegion,
    RecommendedInstrument,
    Sizing,
    StrategyPayload,
)


def test_strategy_payload_has_required_shape():
    payload = StrategyPayload(
        market=MarketRegion.TW,
        trade_date="2026-06-17",
        ticker="2330.TW",
        rating="Buy",
        recommended_instrument=RecommendedInstrument(
            kind=InstrumentKind.SSF,
            symbol="CDF",
            underlying="2330",
            currency="TWD",
            exchange="TAIFEX",
            multiplier=2000,
        ),
        sizing=Sizing(action="Buy", quantity=1, nav=1_000_000),
        executive_summary="High-conviction setup.",
    )

    data = payload.as_jsonable()
    assert data["schema_version"] == "1.0"
    assert data["market"] == "tw"
    assert data["recommended_instrument"]["kind"] == "ssf"
    assert data["sizing"]["quantity"] == 1
