"""Shared data types — the lingua franca between providers, screening, and the allocator.

Panels are wide pandas frames (index = ISO date str ascending, columns = ticker).
Everything else is plain dataclasses so core logic stays pure and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Panel:
    """Wide OHLCV panel. ``institutional`` is net-buy shares per (date, ticker);
    None when the market has no such feed (e.g. US) — consumers must degrade gracefully."""

    close: pd.DataFrame
    volume: pd.DataFrame
    institutional: pd.DataFrame | None = None


@dataclass
class Candidate:
    ticker: str
    date: str
    rank: int
    final_score: float
    scores: dict[str, float] = field(default_factory=dict)
    factors: dict[str, float] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)


# Why the position was opened — drives monitoring: a trend_add is watched on trend
# break, a value_dip only on its invalidation price. "other" is the escape hatch.
SETUP_TYPES = ("value_dip", "pullback_add", "trend_add", "other")


@dataclass
class Holding:
    ticker: str
    weight: float
    theme: str | None = None
    leverage: float = 1.0
    score: float | None = None
    verdict: str | None = None
    # entry state — all optional, absent in pre-T3 holdings files
    entry_price: float | None = None
    entry_date: str | None = None  # ISO date
    setup_type: str | None = None  # one of SETUP_TYPES
    thesis: str | None = None
    invalidation_price: float | None = None

    @property
    def effective_exposure(self) -> float:
        return self.weight * self.leverage


@dataclass
class ProposalCard:
    action: str  # "SWAP" | "TRIM" | "SCALE" | "DECIDE" | "ALERT"
    reason: str
    sell: str | None = None
    buy: str | None = None
    ips_clauses: list[str] = field(default_factory=list)
    score_gap: float | None = None
    friction_pct: float | None = None
    details: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        heads = {
            "SWAP": f"SWAP {self.sell} → {self.buy}",
            "TRIM": f"TRIM {self.sell}",
            # SCALE cuts every position pro rata rather than naming one — sell/buy stay None.
            "SCALE": "SCALE gross exposure",
            # DECIDE is about one position but proposes no side — kill / add / rewrite are
            # the user's three — so its ticker comes from details, not from `sell`.
            "DECIDE": f"DECIDE {self.details.get('ticker', '')}".strip(),
            "ALERT": "ALERT",
        }
        head = heads[self.action]
        lines = [f"### {head}", "", self.reason]
        if self.score_gap is not None:
            lines.append(f"- score gap: {self.score_gap:+.3f}")
        if self.friction_pct is not None:
            lines.append(f"- est. friction: {self.friction_pct:.3f}%")
        if self.ips_clauses:
            lines.append(f"- per your IPS: {', '.join(self.ips_clauses)}")
        return "\n".join(lines)
