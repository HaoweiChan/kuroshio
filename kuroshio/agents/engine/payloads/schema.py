"""Strategy payload schema shared by US and Taiwan pipelines."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


SCHEMA_VERSION = "1.0"


class MarketRegion(str, Enum):
    US = "us"
    TW = "tw"


class InstrumentKind(str, Enum):
    STOCK = "stock"
    SSF = "ssf"
    OPTION = "option"
    CASH = "cash"


class RecommendedInstrument(BaseModel):
    kind: InstrumentKind
    symbol: str
    underlying: str
    currency: str
    exchange: Optional[str] = None
    multiplier: Optional[float] = None
    contract_month: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Sizing(BaseModel):
    action: str
    quantity: Optional[float] = None
    notional: Optional[float] = None
    nav: Optional[float] = None
    nav_currency: Optional[str] = None
    allocation_pct_nav: Optional[float] = None
    initial_margin: Optional[float] = None
    initial_margin_pct_nav: Optional[float] = None
    post_trade_initial_margin: Optional[float] = None
    cap_passed: Optional[bool] = None
    margin_group: Optional[str] = None
    fallback_reason: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class RiskControls(BaseModel):
    max_initial_margin_pct_nav: Optional[float] = None
    stop_loss: Optional[float] = None
    price_target: Optional[float] = None
    time_horizon: Optional[str] = None
    blocked_reason: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class StrategyPayload(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    market: MarketRegion
    trade_date: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ticker: str
    rating: str
    recommended_instrument: RecommendedInstrument
    sizing: Sizing
    executive_summary: str
    risk_controls: RiskControls = Field(default_factory=RiskControls)
    source_reports: Dict[str, str] = Field(default_factory=dict)

    def as_jsonable(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict across Pydantic major versions."""
        if hasattr(self, "model_dump"):
            return self.model_dump(mode="json")
        return self.dict()


def payload_json(payload: StrategyPayload, *, indent: int = 2) -> str:
    if hasattr(payload, "model_dump_json"):
        return payload.model_dump_json(indent=indent)
    return payload.json(indent=indent)

