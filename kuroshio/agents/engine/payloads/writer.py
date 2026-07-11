"""Helpers for building and mirroring strategy payloads."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from kuroshio.agents.engine.agents.utils.rating import parse_rating
from kuroshio.agents.engine.dataflows.utils import safe_ticker_component
from kuroshio.agents.engine.payloads.schema import (
    MarketRegion,
    RecommendedInstrument,
    RiskControls,
    Sizing,
    StrategyPayload,
    payload_json,
)


def _extract_markdown_field(markdown: str, field_name: str) -> Optional[str]:
    pattern = rf"\*\*{re.escape(field_name)}\*\*:\s*(.*?)(?=\n\n\*\*|\Z)"
    match = re.search(pattern, markdown, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def extract_executive_summary(final_trade_decision: str) -> str:
    return (
        _extract_markdown_field(final_trade_decision, "Executive Summary")
        or final_trade_decision.strip().splitlines()[0]
        if final_trade_decision.strip()
        else ""
    )


# The PM decision arrives with English section labels when structured output
# succeeds, but a zh-TW run falls back to free text whose labels come from
# config/i18n/zh-TW.yaml (停損點/目標價/持有期間). Both label styles — and both
# ASCII ':' and fullwidth '：' — must resolve to the same payload field.
_LEVEL_LABELS = {
    "stop_loss": ("Stop Loss", "停損點"),
    "price_target": ("Price Target", "目標價"),
    "time_horizon": ("Time Horizon", "持有期間"),
}


def _labeled_value(markdown: str, field: str) -> Optional[str]:
    """Inline text after the first ``**<label>**:`` line, trying each locale label."""
    for label in _LEVEL_LABELS[field]:
        pattern = rf"\*\*\s*{re.escape(label)}\s*\*\*[:：]\s*([^\n]+)"
        match = re.search(pattern, markdown, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _first_price(value: Optional[str]) -> Optional[float]:
    """First price-like number in a value string: '830美元'→830, '短期1,100美元'
    →1100, '$883'→883, '900–950美元區間'→900. Strips currency marks and thousands
    separators; the parenthetical reasoning after a stop level is ignored because
    only the leading number is taken."""
    if not value:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def extract_time_horizon(final_trade_decision: str) -> Optional[str]:
    return _labeled_value(final_trade_decision, "time_horizon")


def extract_stop_loss(final_trade_decision: str) -> Optional[float]:
    return _first_price(_labeled_value(final_trade_decision, "stop_loss"))


def extract_price_target(final_trade_decision: str) -> Optional[float]:
    return _first_price(_labeled_value(final_trade_decision, "price_target"))


def build_payload_from_state(
    state: Dict[str, Any],
    *,
    market: str,
    instrument: RecommendedInstrument,
    sizing: Sizing,
    risk_controls: Optional[RiskControls] = None,
    run_id: Optional[str] = None,
) -> StrategyPayload:
    final_decision = state.get("final_trade_decision", "")
    controls = risk_controls or RiskControls()
    if controls.time_horizon is None:
        controls.time_horizon = extract_time_horizon(final_decision)
    if controls.stop_loss is None:
        controls.stop_loss = extract_stop_loss(final_decision)
    if controls.price_target is None:
        controls.price_target = extract_price_target(final_decision)

    payload = StrategyPayload(
        market=MarketRegion(market),
        trade_date=str(state["trade_date"]),
        ticker=str(state["company_of_interest"]),
        rating=parse_rating(final_decision),
        recommended_instrument=instrument,
        sizing=sizing,
        executive_summary=extract_executive_summary(final_decision),
        risk_controls=controls,
        source_reports={
            "market": state.get("market_report", ""),
            "chip": state.get("chip_report", ""),
            "sentiment": state.get("sentiment_report", ""),
            "news": state.get("news_report", ""),
            "fundamentals": state.get("fundamentals_report", ""),
            "research": state.get("investment_plan", ""),
            "trader": state.get("trader_investment_plan", ""),
            "portfolio": final_decision,
        },
    )
    if run_id:
        payload.run_id = run_id
    return payload


def mirror_payload(
    payload: StrategyPayload,
    results_dir: str | Path,
) -> Path:
    safe_ticker = safe_ticker_component(payload.ticker)
    directory = (
        Path(results_dir)
        / payload.market.value
        / safe_ticker
        / payload.trade_date
        / "payloads"
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload.run_id}.json"
    path.write_text(payload_json(payload) + "\n", encoding="utf-8")
    return path


def payload_to_pretty_json(payload: StrategyPayload) -> str:
    return json.dumps(payload.as_jsonable(), ensure_ascii=False, indent=2)

