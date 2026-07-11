"""TAIFEX single-stock futures helpers."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import requests
from parsel import Selector

from .finmind import normalize_tw_symbol


MARGINING_TABLE_URL = "https://www.taifex.com.tw/enl/eng5/stockMargining"
STANDARD_STOCK_SSF_MULTIPLIER = 2000
MINI_STOCK_SSF_MULTIPLIER = 100


@dataclass(frozen=True)
class SSFContract:
    symbol: str
    underlying: str
    underlying_name: str = ""
    multiplier: int = STANDARD_STOCK_SSF_MULTIPLIER
    margin_group: Optional[str] = None
    clearing_margin_rate: Optional[float] = None
    maintenance_margin_rate: Optional[float] = None
    initial_margin_rate: Optional[float] = None
    clearing_margin: Optional[float] = None
    maintenance_margin: Optional[float] = None
    initial_margin: Optional[float] = None
    contract_month: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def _to_float(value: str) -> Optional[float]:
    cleaned = value.replace(",", "").replace("%", "").strip()
    if cleaned in {"", "-", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _infer_multiplier(symbol: str, clearing_margin: Optional[float], rate: Optional[float], price: Optional[float] = None) -> int:
    if price and rate and clearing_margin:
        rate_value = rate / 100 if rate > 1 else rate
        implied = clearing_margin / (price * rate_value)
        if implied < 500:
            return MINI_STOCK_SSF_MULTIPLIER
    # TAIFEX mini stock futures are separate 100-share contracts. There is no
    # universal prefix, so unknown rows stay standard unless fixed-margin math
    # proves otherwise.
    return STANDARD_STOCK_SSF_MULTIPLIER


def parse_margining_table(html: str) -> List[SSFContract]:
    selector = Selector(text=html)
    contracts: List[SSFContract] = []

    for row in selector.css("tr"):
        cells = [
            " ".join(cell.css("::text").getall()).strip()
            for cell in row.css("th,td")
        ]
        cells = [cell for cell in cells if cell]
        if len(cells) < 4:
            continue
        if not re.match(r"^\d+$", cells[0]):
            continue
        symbol = cells[1].strip()
        underlying = cells[2].strip()
        if not re.match(r"^\d{4,6}$", underlying):
            continue

        if len(cells) >= 8 and "%" in " ".join(cells[4:8]):
            contracts.append(
                SSFContract(
                    symbol=symbol,
                    underlying=underlying,
                    underlying_name=cells[3],
                    multiplier=STANDARD_STOCK_SSF_MULTIPLIER,
                    margin_group=cells[4],
                    clearing_margin_rate=_to_float(cells[5]),
                    maintenance_margin_rate=_to_float(cells[6]),
                    initial_margin_rate=_to_float(cells[7]),
                )
            )
        elif len(cells) >= 7:
            clearing = _to_float(cells[-3])
            maintenance = _to_float(cells[-2])
            initial = _to_float(cells[-1])
            contracts.append(
                SSFContract(
                    symbol=symbol,
                    underlying=underlying,
                    underlying_name=cells[3],
                    multiplier=_infer_multiplier(symbol, clearing, None),
                    clearing_margin=clearing,
                    maintenance_margin=maintenance,
                    initial_margin=initial,
                )
            )

    return contracts


def fetch_margining_table() -> List[SSFContract]:
    response = requests.get(MARGINING_TABLE_URL, timeout=20)
    response.raise_for_status()
    return parse_margining_table(response.text)


def get_ssf_candidates(
    ticker: str,
    *,
    contracts: Optional[Iterable[SSFContract]] = None,
) -> List[Dict]:
    underlying = normalize_tw_symbol(ticker)
    rows = list(contracts) if contracts is not None else fetch_margining_table()
    return [row.to_dict() for row in rows if row.underlying == underlying]


def has_stock_futures(ticker: str, *, contracts: Optional[Iterable[SSFContract]] = None) -> bool:
    return bool(get_ssf_candidates(ticker, contracts=contracts))


def list_ssf_underlyings(
    *,
    contracts: Optional[Iterable[SSFContract]] = None,
) -> List[Dict]:
    """Collapse the margining table to one entry per underlying security.

    TAIFEX lists several contract rows per underlying (standard 2000-share +
    mini 100-share, multiple delivery months). This returns the deduplicated
    universe of tradable single-stock-futures underlyings, preferring the
    standard contract as the canonical representative for margin fields.

    Each entry: ``{"underlying", "underlying_name", "ticker", "symbol",
    "multiplier"}``. ``ticker`` carries a ``.TW`` suffix for the pipeline; the
    FinMind layer is suffix-agnostic, so an OTC (.TWO) name still resolves by
    its numeric id.
    """
    rows = list(contracts) if contracts is not None else fetch_margining_table()
    by_underlying: Dict[str, SSFContract] = {}
    for row in rows:
        if not row.underlying:
            continue
        existing = by_underlying.get(row.underlying)
        prefer = existing is None or (
            existing.multiplier == MINI_STOCK_SSF_MULTIPLIER
            and row.multiplier == STANDARD_STOCK_SSF_MULTIPLIER
        )
        if prefer:
            by_underlying[row.underlying] = row
    universe: List[Dict] = []
    for underlying, row in sorted(by_underlying.items()):
        universe.append(
            {
                "underlying": underlying,
                "underlying_name": row.underlying_name,
                "ticker": f"{underlying}.TW",
                "symbol": row.symbol,
                "multiplier": row.multiplier,
            }
        )
    return universe


def crawl_ssf_universe(
    cache_path: Optional[str] = None,
    *,
    contracts: Optional[Iterable[SSFContract]] = None,
) -> List[Dict]:
    """Fetch the full SSF underlying universe, optionally caching it to JSON."""
    universe = list_ssf_underlyings(contracts=contracts)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "source": MARGINING_TABLE_URL,
                    "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(universe),
                    "underlyings": universe,
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
    return universe


def rank_underlyings_by_liquidity(
    universe: Iterable[Dict],
    volumes: Dict[str, float],
    *,
    top: Optional[int] = None,
) -> List[Dict]:
    """Sort universe entries by dollar volume (desc), keeping the top ``N``.

    ``volumes`` maps underlying code -> dollar volume. Pure / network-free so
    the ranking is unit-testable; entries missing a volume sort last.
    """
    ranked = sorted(
        universe,
        key=lambda u: volumes.get(u.get("underlying", ""), 0.0),
        reverse=True,
    )
    if top is not None:
        ranked = ranked[:top]
    return ranked


def format_ssf_candidates(ticker: str) -> str:
    try:
        candidates = get_ssf_candidates(ticker)
    except Exception as exc:
        return f"TAIFEX SSF lookup failed for {ticker}: {exc}"
    if not candidates:
        return f"No TAIFEX single-stock futures found for {ticker}."
    lines = [
        "| Symbol | Underlying | Multiplier | Group | Initial Margin Rate | Initial Margin |",
        "|---|---|---:|---|---:|---:|",
    ]
    for c in candidates:
        lines.append(
            "| {symbol} | {underlying} | {multiplier} | {group} | {rate} | {margin} |".format(
                symbol=c.get("symbol"),
                underlying=c.get("underlying"),
                multiplier=c.get("multiplier"),
                group=c.get("margin_group") or "",
                rate=c.get("initial_margin_rate") or "",
                margin=c.get("initial_margin") or "",
            )
        )
    return "\n".join(lines)

