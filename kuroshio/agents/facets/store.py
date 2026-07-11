"""Facet TTL cache — LLM research reports cached per (ticker, facet, date).

Cost-engineering core: a daily portfolio run only regenerates facets whose
cached entry has expired. Storage layout:

    <root>/<ticker>/<facet>-<date>.md

File = YAML frontmatter (generated_at, expires_at, source_events) + report
body. Engine-agnostic — the TradingAgents adapter consumes this later.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

TTL_DAYS: dict[str, int] = {
    "technical": 1,
    "chips": 1,
    "sentiment": 1,
    "news": 1,
    "fundamentals": 7,
}

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*\n?", re.DOTALL)


def _check_safe(name: str, kind: str) -> None:
    """Filenames are built from `name` — a hostile ticker/facet must not escape root."""
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"unsafe {kind}: {name!r}")


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(value, date):
        return value
    raise ValueError(f"not a date: {value!r}")


class FacetStore:
    """Filesystem cache of LLM facet reports, keyed by (ticker, facet, date)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _ticker_dir(self, ticker: str) -> Path:
        _check_safe(ticker, "ticker")
        return self.root / ticker

    def put(
        self,
        ticker: str,
        facet: str,
        content: str,
        asof: str,
        ttl_days: int | None = None,
        source_events: list[str] | None = None,
    ) -> Path:
        _check_safe(facet, "facet")
        ttl = TTL_DAYS.get(facet, 1) if ttl_days is None else ttl_days
        expires_at = date.fromisoformat(asof) + timedelta(days=ttl)
        path = self._ticker_dir(ticker) / f"{facet}-{asof}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = (
            f"generated_at: {datetime.now().isoformat()}\n"
            f"expires_at: {expires_at.isoformat()}\n"
            f"source_events: {source_events or []}\n"
        )
        path.write_text(f"---\n{frontmatter}---\n{content}", encoding="utf-8")
        return path

    def get(self, ticker: str, facet: str, asof: str) -> str | None:
        """Freshest entry with date <= asof and still valid (expires_at > asof)."""
        _check_safe(facet, "facet")
        ticker_dir = self._ticker_dir(ticker)
        if not ticker_dir.is_dir():
            return None
        asof_d = date.fromisoformat(asof)
        best: tuple[date, str] | None = None
        for path in ticker_dir.glob(f"{facet}-*.md"):
            try:
                entry_d = date.fromisoformat(path.stem[len(facet) + 1 :])
                if entry_d > asof_d:
                    continue
                text = path.read_text(encoding="utf-8")
                match = _FRONTMATTER_RE.match(text)
                meta = yaml.safe_load(match.group(1))
                if _as_date(meta["expires_at"]) <= asof_d:
                    continue
                body = text[match.end() :]
            except Exception:
                continue  # corrupt/unparseable entry — treat as missing, never raise
            if best is None or entry_d > best[0]:
                best = (entry_d, body)
        return best[1] if best else None

    def invalidate(self, ticker: str, facet: str | None = None) -> int:
        """Delete matching entries (facet None = all facets for ticker). Returns count deleted."""
        ticker_dir = self._ticker_dir(ticker)
        if not ticker_dir.is_dir():
            return 0
        if facet is not None:
            _check_safe(facet, "facet")
        paths = list(ticker_dir.glob(f"{facet}-*.md" if facet else "*.md"))
        for path in paths:
            path.unlink()
        return len(paths)

    def plan(self, tickers: list[str], facets: list[str], asof: str) -> dict[str, dict[str, str | None]]:
        """Daily-run entry point: cached body per (ticker, facet), or None if stale."""
        return {t: {f: self.get(t, f, asof) for f in facets} for t in tickers}
