"""Portfolio state models used by market-specific sizing logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AccountState:
    account: str
    currency: str
    as_of: Optional[str]
    nav: Optional[float]
    source_path: str
    stale: bool = False
    metrics: Dict[str, float] = field(default_factory=dict)
    positions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioSnapshot:
    market: str
    currency: str
    as_of: Optional[str]
    nav: Optional[float]
    accounts: List[AccountState] = field(default_factory=list)
    stale: bool = False
    missing_accounts: List[str] = field(default_factory=list)

    @property
    def existing_initial_margin(self) -> Optional[float]:
        total = 0.0
        found = False
        for account in self.accounts:
            value = account.metrics.get("initial_margin")
            if value is not None:
                total += value
                found = True
        return total if found else None


def snapshot_to_dict(snapshot: PortfolioSnapshot) -> Dict[str, Any]:
    return {
        "market": snapshot.market,
        "currency": snapshot.currency,
        "as_of": snapshot.as_of,
        "nav": snapshot.nav,
        "stale": snapshot.stale,
        "missing_accounts": list(snapshot.missing_accounts),
        "existing_initial_margin": snapshot.existing_initial_margin,
        "accounts": [
            {
                "account": account.account,
                "currency": account.currency,
                "as_of": account.as_of,
                "nav": account.nav,
                "source_path": account.source_path,
                "stale": account.stale,
                "metrics": dict(account.metrics),
                "positions": list(account.positions),
            }
            for account in snapshot.accounts
        ],
    }

