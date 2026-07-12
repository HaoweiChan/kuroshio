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


@dataclass
class Holding:
    ticker: str
    weight: float
    theme: str | None = None
    leverage: float = 1.0
    score: float | None = None
    verdict: str | None = None

    @property
    def effective_exposure(self) -> float:
        return self.weight * self.leverage


@dataclass
class ProposalCard:
    action: str  # "SWAP" | "TRIM" | "ALERT"
    reason: str
    sell: str | None = None
    buy: str | None = None
    ips_clauses: list[str] = field(default_factory=list)
    score_gap: float | None = None
    friction_pct: float | None = None
    details: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        heads = {"SWAP": f"SWAP {self.sell} → {self.buy}", "TRIM": f"TRIM {self.sell}", "ALERT": "ALERT"}
        head = heads[self.action]
        lines = [f"### {head}", "", self.reason]
        if self.score_gap is not None:
            lines.append(f"- score gap: {self.score_gap:+.3f}")
        if self.friction_pct is not None:
            lines.append(f"- est. friction: {self.friction_pct:.3f}%")
        if self.ips_clauses:
            lines.append(f"- per your IPS: {', '.join(self.ips_clauses)}")
        return "\n".join(lines)
