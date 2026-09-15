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
    None when the market has no such feed (e.g. US) — consumers must degrade gracefully.

    ``high``/``low`` are the session extremes on ``close``'s index and columns. They are
    None on a panel built by hand or before TASK-11: the true range — and so the ATR the
    allocator's stop ratchet trails by — is all that reads them, and that simply does not
    run without them."""

    close: pd.DataFrame
    volume: pd.DataFrame
    institutional: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None


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

# How Holding.entry_date was sourced (TASK-18) — see Holding.entry_date_source.
ENTRY_DATE_SOURCES = ("manifest_first_seen", "snapshot_first_seen")


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
    # how entry_date was sourced (TASK-18) — "manifest_first_seen" (a real fill) or
    # "snapshot_first_seen" (a tracking start, not a fill: kept on the Holding so
    # core/allocator can name the row on its coverage line, but entry_date itself is
    # dropped before construction — see cli.py:_holdings_from_yaml). None = pre-TASK-18
    # file, same as manifest_first_seen.
    entry_date_source: str | None = None

    @property
    def effective_exposure(self) -> float:
        return self.weight * self.leverage


# The three `to_markdown()` detail-line labels, by language — TASK-22. The `### ` head
# line and every other word `propose()` did not translate stay English regardless: only
# these three labels read `lang`, so this table is deliberately tiny (contrast
# `core/allocator/engine.CARD_TEXT`, which holds every card `reason`).
_DETAIL_LABELS: dict[str, dict[str, str]] = {
    "en": {"score_gap": "score gap", "friction": "est. friction", "ips": "per your IPS"},
    "zh": {"score_gap": "評分差距", "friction": "預估摩擦成本", "ips": "依你的 IPS"},
}


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
    # TASK-22: the language `reason` was rendered in — set by `core.allocator.propose()`
    # on every card it returns, English by default so a card built by hand (as most
    # tests do) renders exactly as it always did.
    lang: str = "en"

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
        labels = {**_DETAIL_LABELS["en"], **_DETAIL_LABELS.get(self.lang, {})}
        lines = [f"### {head}", "", self.reason]
        if self.score_gap is not None:
            lines.append(f"- {labels['score_gap']}: {self.score_gap:+.3f}")
        if self.friction_pct is not None:
            lines.append(f"- {labels['friction']}: {self.friction_pct:.3f}%")
        if self.ips_clauses:
            lines.append(f"- {labels['ips']}: {', '.join(self.ips_clauses)}")
        return "\n".join(lines)
