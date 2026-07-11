# TradingAgents/graph/facet_cache.py
"""Per-ticker analyst-report cache ("facets") — Kuroshio Phase 1 F1.

Lets a daily rerun skip analysts whose report is still fresh: the cached
content seeds the graph's initial state for those report fields instead of
re-running the LLM + tools for that analyst. History is NOT kept here (it
already lives in ``full_states_log_<date>.json`` per ticker); this store is
latest-only.

Freshness rules:
  - market / social / news / chip: fresh iff ``trade_date`` matches exactly
    (recomputed every trading day).
  - fundamentals: fresh iff within ``ttl_days`` calendar days of the cached
    ``trade_date`` (default 7; slow-moving data, and keeps the free-tier
    Alpha Vantage quota alive).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from kuroshio.agents.engine.dataflows.utils import safe_ticker_component

from .analyst_execution import ANALYST_NODE_SPECS

logger = logging.getLogger(__name__)

TTL_FACETS = {"fundamentals"}


def facet_path(facets_dir: str | Path, ticker: str, facet: str) -> Path:
    return Path(facets_dir) / safe_ticker_component(ticker).upper() / f"{facet}.json"


def load_facet(facets_dir: str | Path, ticker: str, facet: str) -> dict[str, Any] | None:
    path = facet_path(facets_dir, ticker, facet)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("facet cache unreadable, treating as stale: %s (%s)", path, exc)
        return None


def is_fresh(record: dict[str, Any] | None, trade_date: str, facet: str, ttl_days: int) -> bool:
    if not record or not record.get("content") or not record.get("trade_date"):
        return False
    try:
        cached = date.fromisoformat(record["trade_date"])
        current = date.fromisoformat(str(trade_date))
    except ValueError:
        return False
    if facet in TTL_FACETS:
        return abs((current - cached).days) <= ttl_days
    return cached == current


def plan_facets(
    *,
    facets_dir: str | Path,
    ticker: str,
    trade_date: str,
    available_facets: list[str],
    ttl_days: int = 7,
    force_fresh: frozenset[str] = frozenset(),
) -> tuple[list[str], dict[str, str]]:
    """Return ``(stale_facet_keys, seed_reports)`` for one ticker's run.

    ``available_facets`` is the analyst-key universe for the market (4 for
    US, 5 for TW incl. chip). ``force_fresh`` treats a facet as fresh even
    past its TTL as long as a cached record exists (caller-side AV-refresh
    budget downgrade, F3.2) — it never fabricates a facet that was never
    cached.

    If every facet resolves fresh, ``build_analyst_execution_plan`` cannot
    run with an empty selection (it requires >=1 analyst), so the cheapest/
    always-daily facet (``market``) is forced stale and dropped from the
    seed so the graph still has a shape.
    """
    stale: list[str] = []
    seed: dict[str, str] = {}
    for facet in available_facets:
        record = load_facet(facets_dir, ticker, facet)
        fresh = is_fresh(record, trade_date, facet, ttl_days)
        if not fresh and facet in force_fresh and record and record.get("content"):
            fresh = True
        if fresh:
            seed[ANALYST_NODE_SPECS[facet].report_key] = record["content"]
        else:
            stale.append(facet)

    if not stale:
        forced = "market" if "market" in available_facets else available_facets[0]
        stale = [forced]
        seed.pop(ANALYST_NODE_SPECS[forced].report_key, None)
        logger.info(
            "facet cache: all facets fresh for %s on %s; forcing %s refresh so "
            "the graph has a shape", ticker, trade_date, forced,
        )
    return stale, seed


def write_facet(
    facets_dir: str | Path, ticker: str, facet: str, trade_date: str, content: str, lang: str,
) -> None:
    path = facet_path(facets_dir, ticker, facet)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "facet": facet,
        "ticker": ticker,
        "trade_date": str(trade_date),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lang": lang,
        "content": content,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def write_back(
    *,
    facets_dir: str | Path,
    ticker: str,
    trade_date: str,
    lang: str,
    regenerated_facets: list[str],
    final_state: dict[str, Any],
) -> None:
    """Persist only the facets actually regenerated this run.

    Seeded (cache-hit) facets must NOT be rewritten here — doing so would
    reset their ``trade_date`` and defeat the fundamentals TTL.
    """
    for facet in regenerated_facets:
        report_key = ANALYST_NODE_SPECS[facet].report_key
        content = final_state.get(report_key, "")
        if content:
            write_facet(facets_dir, ticker, facet, trade_date, content, lang)
