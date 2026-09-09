"""kuroshio CLI — screen | backtest | simulate | propose | ips-validate | research | evaluate | mcp.

Stdlib argparse only (no click/typer/rich). Providers and yaml are imported
lazily inside each command so ``kuroshio --help`` stays fast and never
touches the network. Network calls happen only in the ``screen``, ``backtest``,
``simulate``, ``research``, ``evaluate`` and — when a score is missing from the
input files — ``propose``. ``research`` additionally requires the optional
``agents`` extra (LLM engine) and exits 2 with an install hint if it's missing.
``mcp`` requires the optional ``mcp`` extra and exits 2 the same way; it runs a
stdio MCP server exposing the engine's dataflows (and screen/propose/record_rating)
as tools for a Claude Code session, with no LLM calls of its own (TASK-10).

``screen`` and ``research`` append to a plain-file ledger (``kuroshio.core.ledger``)
by default — ``--no-ledger`` opts out; ``evaluate`` reads that ledger back and
prints realized forward performance.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import dataclasses
import datetime
import json
import math
import os
import sys
from collections.abc import Callable
from pathlib import Path

from kuroshio.core.screening import PROFILES, get_profile
from kuroshio.types import ENTRY_DATE_SOURCES, SETUP_TYPES, Candidate, Holding


def _parse_tickers(tickers: str | None, tickers_file: str | None) -> list[str]:
    if tickers_file:
        out = []
        for line in Path(tickers_file).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
        return out
    return [t.strip() for t in (tickers or "").split(",") if t.strip()]


# --- point-in-time membership (--members-file) ------------------------------


def _load_members(path: str) -> list[tuple[str, frozenset[str]]]:
    """Parse a `date,tickers` CSV (produced by scripts/sp500_members.py) into ascending
    (date, tickers) snapshots. Membership on a given date is the tickers of the LAST
    snapshot whose date <= that date; a date before the first snapshot uses the first
    snapshot (see _members_at). Raises ValueError on a missing/wrong header or an empty
    file — callers should catch it the way _holdings_from_yaml's ValueError is caught."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["date", "tickers"]:
            raise ValueError(f"{path}: expected header 'date,tickers', got {reader.fieldnames!r}")
        rows = [(row["date"], frozenset(row["tickers"].split())) for row in reader]
    if not rows:
        raise ValueError(f"{path}: no membership rows")
    return sorted(rows, key=lambda r: r[0])


def _members_at(snapshots: list[tuple[str, frozenset[str]]], asof: str) -> frozenset[str]:
    """Membership on `asof`: the tickers of the last snapshot with date <= asof, or the
    first snapshot if asof is before every snapshot date."""
    dates = [d for d, _ in snapshots]
    i = max(bisect.bisect_right(dates, asof) - 1, 0)
    return snapshots[i][1]


def _load_universe(path: str) -> list[str]:
    """`propose --universe-file` loader: a `date,tickers` snapshot (the last row, sorted)
    or a plain newline ticker list (`_parse_tickers`'s format). Raises ValueError on an
    empty file — callers catch it the way holdings/candidates file errors are caught."""
    try:
        with open(path) as f:
            first_line = f.readline().rstrip("\n\r")
    except OSError as exc:  # a missing universe file is a file error, not a traceback
        raise ValueError(f"{path}: {exc.strerror}") from exc
    if first_line == "date,tickers":
        snapshots = _load_members(path)
        return sorted(snapshots[-1][1])
    tickers = _parse_tickers(None, path)
    if not tickers:
        raise ValueError(f"{path}: no tickers")
    return tickers


def _pit_screen(
    screen_fn: Callable[..., list[Candidate]], snapshots: list[tuple[str, frozenset[str]]]
) -> Callable[..., list[Candidate]]:
    """Wrap a screen_fn so its candidates are filtered to that date's point-in-time
    membership. Ranks are left as screen_fn produced them (gaps are fine — callers sort
    by rank, not by position)."""

    def screen(panel, asof: str | None = None, **kw) -> list[Candidate]:
        resolved_asof = asof if asof is not None else str(panel.close.index[-1])
        members = _members_at(snapshots, resolved_asof)
        return [c for c in screen_fn(panel, asof=asof, **kw) if c.ticker in members]

    return screen


def _resolve_universe(args: argparse.Namespace):
    """(tickers to fetch, point-in-time snapshots or None) for backtest/simulate, or None
    after printing the error — the two commands share one universe contract."""
    if args.members_file:
        try:
            snapshots = _load_members(args.members_file)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
        return sorted(set().union(*(s for _, s in snapshots))), snapshots
    tickers = _parse_tickers(args.tickers, args.tickers_file)
    if not tickers:
        print("error: --tickers / --tickers-file resolved to zero tickers", file=sys.stderr)
        return None
    return tickers, None


def _survivorship_caveat(members_file: str | None) -> str:
    if members_file:
        return (
            f"\ncaveat: membership is point-in-time from {members_file}, but names whose price "
            "history the provider no longer carries could not be held — residual survivorship "
            "bias remains."
        )
    return (
        "\ncaveat: the supplied tickers ARE the universe — passing only today's survivors "
        "introduces survivorship bias; point-in-time membership is on you."
    )


def _load_yaml(path: str):
    import yaml

    return yaml.safe_load(Path(path).read_text()) or []


def _holdings_from_yaml(path: str) -> list[Holding]:
    known = {f.name for f in dataclasses.fields(Holding)}
    holdings = []
    for item in _load_yaml(path):
        where = f"{path}: {item.get('ticker', '?')}"
        for key in item:
            if key not in known:
                raise ValueError(f"{where}: unknown key {key!r} (expected one of {sorted(known)})")
        if item.get("setup_type") is not None and item["setup_type"] not in SETUP_TYPES:
            raise ValueError(
                f"{where}: unknown setup_type {item['setup_type']!r} "
                f"(expected one of {list(SETUP_TYPES)})"
            )
        entry_date_source = item.get("entry_date_source")
        if entry_date_source is not None and entry_date_source not in ENTRY_DATE_SOURCES:
            raise ValueError(
                f"{where}: unknown entry_date_source {entry_date_source!r} "
                f"(expected one of {list(ENTRY_DATE_SOURCES)})"
            )
        if entry_date_source == "snapshot_first_seen":
            # a tracking start is not a fill: a running high/low measured from it would
            # ratchet the stop above the entry and breach on day one (TASK-18). The
            # allocator names the ticker on its coverage line for this — see engine.py
            # step 3c — off entry_date_source, which is kept.
            item.pop("entry_date", None)
        if item.get("entry_date") is not None:
            # unquoted `2025-01-15` comes back from PyYAML as a datetime.date; the field is ISO str
            item["entry_date"] = str(item["entry_date"])
        holdings.append(Holding(**item))
    return holdings


# candidates.yml is not a Candidate dump: `verdict`/`theme` are separate maps the
# allocator takes, and the computed fields (date/rank/scores/...) are not user input.
_CANDIDATE_KEYS = ("ticker", "final_score", "verdict", "theme")


def _candidates_from_yaml(path: str) -> tuple[list[Candidate], dict[str, str], dict[str, str]]:
    today = datetime.date.today().isoformat()
    candidates: list[Candidate] = []
    verdicts: dict[str, str] = {}
    themes: dict[str, str] = {}
    for item in _load_yaml(path):
        where = f"{path}: {item.get('ticker', '?')}"
        for key in item:
            if key not in _CANDIDATE_KEYS:
                raise ValueError(
                    f"{where}: unknown key {key!r} (expected one of {sorted(_CANDIDATE_KEYS)})"
                )
        ticker = item["ticker"]
        if item.get("verdict") is not None:
            verdicts[ticker] = item["verdict"]
        if item.get("theme") is not None:
            themes[ticker] = item["theme"]
        # final_score may be absent — cmd_propose ranks it with the rest of the file and
        # drops (loudly) whatever Stage-1 rejects, before any Candidate reaches propose().
        candidates.append(Candidate(ticker=ticker, date=today, rank=0, final_score=item.get("final_score")))
    return candidates, verdicts, themes


# --- screen ------------------------------------------------------------------


def _print_screen_table(market: str, candidates: list[Candidate], asof_fallback: str = "n/a") -> None:
    # 0 candidates is a normal outcome (strict Stage-1 gates); show which session
    # was screened so it doesn't read as a fetch failure.
    asof = candidates[0].date if candidates else asof_fallback
    print(f"market={market} asof={asof} candidates={len(candidates)}")
    if any(c.flags.get("degraded") for c in candidates):
        print("notice: institutional data unavailable — institution factor dropped, momentum reweighted")
    if not candidates:
        return

    factor_keys: list[str] = []
    for c in candidates:
        for k in c.scores:
            if k not in factor_keys:
                factor_keys.append(k)

    headers = ["rank", "ticker", "final"] + factor_keys + ["flags"]
    rows = []
    for c in candidates:
        flags = []
        if c.flags.get("is_60d_high"):
            flags.append("★")
        if c.flags.get("crowded"):
            flags.append("crowded")
        if c.flags.get("degraded"):
            flags.append("degraded")
        row = [str(c.rank), c.ticker, f"{c.final_score:.3f}"]
        row += [f"{c.scores[k]:.2f}" if k in c.scores else "" for k in factor_keys]
        row.append(" ".join(flags))
        rows.append(row)

    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(cell.ljust(w) for cell, w in zip(cells, widths))  # noqa: E731
    print(line(headers))
    for row in rows:
        print(line(row))


def _candidate_to_dict(c: Candidate) -> dict:
    return {
        "ticker": c.ticker, "date": c.date, "rank": c.rank, "final_score": c.final_score,
        "scores": c.scores, "factors": c.factors, "flags": c.flags,
    }


def _append_score_rows(
    market: str, provider, panel, candidates: list[Candidate], snapshot_top: int
) -> None:
    from kuroshio.core import ledger

    rows = []
    for i, c in enumerate(candidates):
        close = None
        if c.ticker in panel.close.columns and c.date in panel.close.index:
            val = panel.close.loc[c.date, c.ticker]
            close = float(val) if val == val else None  # val == val is False for NaN

        fundamentals = None
        if i < snapshot_top:
            try:
                snap = provider.fetch_fundamentals(c.ticker)
            except Exception:
                snap = None
            if snap:
                fundamentals = {**snap, "asof": c.date}

        rows.append({
            "date": c.date, "market": market, "profile": market, "ticker": c.ticker,
            "rank": c.rank, "final_score": c.final_score, "scores": c.scores,
            "factors": c.factors, "close": close, "fundamentals": fundamentals,
        })

    path = ledger.ledger_dir() / ledger.SCORES
    ledger.append(path, rows)
    print(f"ledger: {len(rows)} rows -> {path}", file=sys.stderr)


def cmd_screen(args: argparse.Namespace) -> int:
    import yaml

    from kuroshio.providers import get_provider

    market = args.market
    profile = get_profile(market)
    provider_name = args.provider or profile.default_provider
    tickers = _parse_tickers(args.tickers, args.tickers_file)
    if not tickers:
        print("error: --tickers / --tickers-file resolved to zero tickers", file=sys.stderr)
        return 2

    sector_map = None
    if args.sector_map:
        sector_map = yaml.safe_load(Path(args.sector_map).read_text()) or {}

    fetch_tickers = list(tickers)
    extra = {profile.benchmark} if profile.benchmark else set()
    if profile.accepts_sector_map and sector_map:
        extra |= set(sector_map.values())
    fetch_tickers += [t for t in extra if t not in fetch_tickers]

    try:
        provider = get_provider(provider_name)
        panel = provider.fetch_panel(fetch_tickers, profile.lookback_days, end=args.asof)
    except ImportError:
        print(
            f'error: the {provider_name!r} provider is not installed. '
            f'Run: pip install "kuroshio[{provider_name}]"',
            file=sys.stderr,
        )
        return 2

    screen_kwargs = {"sector_map": sector_map} if profile.accepts_sector_map else {}
    if args.no_gate:
        # Fix 2 (kuroshio<->hermes glue): score every requested ticker without the
        # Stage-1 breakout gate — used to rank incumbent holdings that aren't fresh
        # breakouts. `tickers` (not fetch_tickers) so benchmark/sector-ETF reference
        # columns never get scored as if they were candidates.
        candidates = profile.score_names(panel, tickers=tickers, asof=args.asof, **screen_kwargs)
    else:
        candidates = profile.screen(panel, asof=args.asof, **screen_kwargs)

    top = candidates[: args.top]
    if args.json:
        print(json.dumps([_candidate_to_dict(c) for c in top]))
    else:
        last_session = str(panel.close.index[-1]) if len(panel.close.index) else "n/a"
        _print_screen_table(market, top, asof_fallback=args.asof or last_session)

    if not args.no_ledger:
        # every gated candidate, not just the printed top: a realized rank-IC over 20
        # names is noise, over the whole pool it is a measurement.
        _append_score_rows(market, provider, panel, candidates, args.snapshot_top)
    return 0


# --- backtest ------------------------------------------------------------


def cmd_backtest(args: argparse.Namespace) -> int:
    import yaml

    from kuroshio.core.backtest import walkforward
    from kuroshio.providers import get_provider

    market = args.market
    profile = get_profile(market)
    provider_name = args.provider or profile.default_provider
    universe = _resolve_universe(args)
    if universe is None:
        return 2
    tickers, snapshots = universe

    sector_map = None
    if args.sector_map:
        sector_map = yaml.safe_load(Path(args.sector_map).read_text()) or {}

    # benchmark first: providers/yf.py:_shape_panel filters the whole panel to the first
    # ticker that resolved as its reference row, so a delisted/unresolved name earlier in
    # the list must never land in that slot and truncate the panel to its lifetime.
    fetch_tickers = [profile.benchmark] if profile.benchmark else []
    fetch_tickers += [t for t in tickers if t not in fetch_tickers]
    if profile.accepts_sector_map and sector_map:
        fetch_tickers += [t for t in sector_map.values() if t not in fetch_tickers]

    # indicator warmup + horizon headroom; see MarketProfile.warmup_days for the derivation.
    lookback_days = args.weeks * 7 + profile.warmup_days

    try:
        provider = get_provider(provider_name)
        panel = provider.fetch_panel(fetch_tickers, lookback_days)
    except ImportError:
        print(
            f'error: the {provider_name!r} provider is not installed. '
            f'Run: pip install "kuroshio[{provider_name}]"',
            file=sys.stderr,
        )
        return 2

    screen_kwargs = {"sector_map": sector_map} if profile.accepts_sector_map else {}
    screen_fn = _pit_screen(profile.screen, snapshots) if snapshots else profile.screen
    result = walkforward(
        panel, screen_fn, horizon=args.horizon, top_k=args.top,
        benchmark=profile.benchmark, min_history=profile.min_history, **screen_kwargs,
    )

    print(result.to_markdown())
    print(_survivorship_caveat(args.members_file))
    return 0


# --- simulate --------------------------------------------------------------


def cmd_simulate(args: argparse.Namespace) -> int:
    import yaml

    from kuroshio.core.ips import parse_ips, validate
    from kuroshio.core.simulate import simulate
    from kuroshio.providers import get_provider

    ips = parse_ips(args.ips)
    problems = validate(ips)
    if problems:
        for p in problems:
            print(p)
        return 2

    market = args.market
    profile = get_profile(market)
    provider_name = args.provider or profile.default_provider
    universe = _resolve_universe(args)
    if universe is None:
        return 2
    tickers, snapshots = universe

    sector_map = None
    if args.sector_map:
        sector_map = yaml.safe_load(Path(args.sector_map).read_text()) or {}

    # benchmark first: providers/yf.py:_shape_panel filters the whole panel to the first
    # ticker that resolved as its reference row, so a delisted/unresolved name earlier in
    # the list must never land in that slot and truncate the panel to its lifetime.
    fetch_tickers = [profile.benchmark] if profile.benchmark else []
    fetch_tickers += [t for t in tickers if t not in fetch_tickers]
    if profile.accepts_sector_map and sector_map:
        fetch_tickers += [t for t in sector_map.values() if t not in fetch_tickers]

    # same warmup headroom as backtest — see MarketProfile.warmup_days.
    lookback_days = args.weeks * 7 + profile.warmup_days

    try:
        provider = get_provider(provider_name)
        panel = provider.fetch_panel(fetch_tickers, lookback_days)
    except ImportError:
        print(
            f'error: the {provider_name!r} provider is not installed. '
            f'Run: pip install "kuroshio[{provider_name}]"',
            file=sys.stderr,
        )
        return 2

    screen_kwargs = {"sector_map": sector_map} if profile.accepts_sector_map else {}
    screen_fn = _pit_screen(profile.screen, snapshots) if snapshots else profile.screen
    result = simulate(
        panel, screen_fn, profile.score_names, ips, market,
        step=args.step, top_k=args.top, benchmark=profile.benchmark,
        min_history=profile.min_history, **screen_kwargs,
    )

    print(result.to_markdown())
    print(_survivorship_caveat(args.members_file))
    return 0


# --- propose -------------------------------------------------------------


def _score_missing(
    holdings: list[Holding],
    challengers: list[Candidate],
    profile,
    panel,
    hurdle: float,
    universe: list[str] | None = None,
):
    """Fill in the scores the user didn't hand-type; return (surviving challengers, auto-filled).

    ONE cross-section for everybody: every ticker in the input files is ranked once by
    the market's ungated ``score_names``, so an incumbent's ``score`` and a challenger's
    ``final_score`` are literally the same number for the same name — the scale the swap
    gate is allowed to subtract on (the contract on ``core/screening/us.py:score_names``).
    The gated ``screen`` decides challenger *eligibility* only: a name Stage-1 rejects is
    not a challenger, and is reported rather than dropped in silence.

    ``hurdle`` is the full swap bar (turnover hurdle + friction — ``swap_hurdle``), and
    below ``floor(profile.min_rank_weight / hurdle) + 2`` names nothing is auto-filled:
    the allocator's "no holding has a screener score" ALERT stands, because a refusal
    beats a fabricated number.

    That floor is a **heuristic, not a theorem**. It scales one pctrank step, ``1/(n-1)``,
    by ``min_rank_weight`` — the largest share of the score any single pctrank carries in
    the market's fully degraded composite — and asks whether the result is already as big
    as the hurdle. In a pool that small the scores are spread thinly enough that the
    hurdle may be doing no work at all, so ``propose`` declines to auto-fill rather than
    decide case by case. It over-refuses on purpose, and in two directions: the real
    composite is usually finer than the degraded one (TW with institutional flow present
    carries 1/6 per momentum rank, not 1/3 — R17), and where the surviving weights are
    unequal the score does not land on a ``min_rank_weight`` grid at all, so smaller gaps
    than the formula suggests are reachable (US degraded is 0.625/0.375 — R19). Both make
    the floor conservative, never permissive. Do not sharpen it into an exact minimum
    step: three rounds of this PR tried, and each precise claim was false in the
    configuration it was not derived on. The cost of over-refusing is one manual
    ``kuroshio screen``; the cost of a wrong exact claim is a fabricated gap on a card.

    Above that size the score is still only a percentile **within this pool** — pctrank
    pins its extremes to 0.000/1.000 however tightly the factors cluster — so the second
    return value maps each auto-filled ticker to the pool it was ranked in and ``propose``
    discloses that on the card itself (see ``core/allocator/engine.py``). Hand-typed
    scores are untouched and undisclosed.

    ``universe`` (``propose --universe-file``) adds a third source of names to the pool
    alongside holdings and challengers — an index-sized cross-section rather than "the
    user's own files". It is not a separate refusal path: ``need`` is unchanged and the
    same ``len(ranked) < need`` check still applies, it just no longer fires in practice
    once the pool is index-sized (a universe too thin on history to clear ``need`` is not
    big by construction and still gets the refusal).
    """
    names = list(
        dict.fromkeys(
            [h.ticker for h in holdings] + [c.ticker for c in challengers] + list(universe or [])
        )
    )
    ranked = {c.ticker: c.final_score for c in profile.score_names(panel, tickers=names)}
    need = math.floor(profile.min_rank_weight / hurdle) + 2
    if len(ranked) < need:
        print(
            f"notice: {len(ranked)} name(s) in your files is too small a cross-section to "
            f"rank against a turnover hurdle of {hurdle:.3f}. propose auto-fills scores "
            f"only at {need} names or more — a deliberately conservative floor, read off "
            f"this market's single coarsest factor weight rather than worked out exactly: "
            f"in a pool this small the scores may be spread too thinly for the hurdle to "
            f"be telling you anything, and propose would rather refuse than decide that "
            f"case by case. It may well be refusing a pool your hurdle could have judged "
            f"fine. No score was auto-filled — hand-type one, or list more names.",
            file=sys.stderr,
        )
        ranked = {}
    eligible = {c.ticker for c in profile.screen(panel)}
    auto: dict[str, int] = {}

    for h in holdings:
        if h.score is None and h.ticker in ranked:
            h.score = ranked[h.ticker]
            auto[h.ticker] = len(ranked)

    kept, dropped = [], []
    for c in challengers:
        if c.final_score is None:
            if c.ticker not in eligible or c.ticker not in ranked:
                dropped.append(c.ticker)
                continue
            c.final_score = ranked[c.ticker]
            auto[c.ticker] = len(ranked)
        kept.append(c)
    if dropped:
        why = "did not pass the Stage-1 gate" if ranked else "could not be auto-scored"
        print(
            f"notice: {len(dropped)} candidate(s) had no hand-typed final_score and "
            f"{why}: {', '.join(dropped)}",
            file=sys.stderr,
        )
    return kept, auto


def _run_propose(
    ips_path: str,
    holdings_path: str,
    market: str,
    *,
    candidates_path: str | None = None,
    universe_file: str | None = None,
    swaps_this_week: int = 0,
    provider_name: str | None = None,
):
    """Core of ``propose``: (cards, None) on success, (None, message_lines) on an
    invalid IPS or a bad holdings/candidates/universe/provider input.

    Shared by ``cmd_propose`` (CLI) and the MCP ``propose`` tool, so both take the
    exact same path from an IPS + holdings file to proposal cards (TASK-10) — the
    CLI prints ``message_lines`` (plain to stdout for IPS ``validate()`` problems,
    ``error: ...``-prefixed to stderr for a file/provider problem) and exits 2; the
    MCP tool just joins them into its returned string.
    """
    from kuroshio.core.allocator import propose
    from kuroshio.core.allocator.engine import MONITORED_SETUPS, swap_hurdle
    from kuroshio.core.allocator.signals import book_vol as compute_book_vol
    from kuroshio.core.allocator.signals import monitor_inputs, trail_inputs
    from kuroshio.core.ips import parse_ips, validate
    from kuroshio.providers import get_provider

    ips = parse_ips(ips_path)
    problems = validate(ips)
    if problems:
        return None, problems

    challengers, verdicts, themes, auto_scored = [], {}, {}, {}
    universe: list[str] | None = None
    try:
        holdings = _holdings_from_yaml(holdings_path)
        if candidates_path:
            challengers, verdicts, themes = _candidates_from_yaml(candidates_path)
        if universe_file:
            universe = _load_universe(universe_file)
    except ValueError as exc:
        return None, [f"error: {exc}"]

    # TASK-7: with a universe, an auto-filled score is a percentile of that cross-section
    # rather than of "your own files" — the SWAP card names which pool it came from.
    pool_name = (
        f"the universe in {Path(universe_file).name}" if universe_file
        else "your own files"
    )

    # The user is no longer the integration layer: anything without a hand-typed
    # score gets one from the screener, and a holding a monitoring rule can read gets
    # this session's price — its thesis rule if it has a monitored setup_type, the
    # loss-from-entry rule if it has an entry_price, which dispatches on no setup at
    # all. A set caps.book_vol_target_pct needs a panel too, for signals.book_vol —
    # none of that needed -> no fetch, no network.
    prices: dict[str, float] = {}
    ma50: dict[str, float] = {}
    running_high: dict[str, float] = {}
    atr14: dict[str, float] = {}
    min_close: dict[str, float] = {}
    asof = None
    book_vol: float | None = None
    need_scores = any(h.score is None for h in holdings) or any(
        c.final_score is None for c in challengers
    )
    monitored = any(h.setup_type in MONITORED_SETUPS or h.entry_price for h in holdings)
    vol_targeted = ips.caps.book_vol_target_pct is not None
    if need_scores or monitored or vol_targeted:
        profile = get_profile(market)
        provider_name = provider_name or profile.default_provider
        if universe is not None:
            # first: providers/yf.py filters the panel to its first resolved ticker
            fetch_tickers = [profile.benchmark] if profile.benchmark else []
            fetch_tickers += [
                t for t in dict.fromkeys([h.ticker for h in holdings] + [c.ticker for c in challengers])
                if t not in fetch_tickers
            ]
            fetch_tickers += [t for t in universe if t not in fetch_tickers]
        else:
            fetch_tickers = list(
                dict.fromkeys([h.ticker for h in holdings] + [c.ticker for c in challengers])
            )
            if profile.benchmark and profile.benchmark not in fetch_tickers:
                fetch_tickers.append(profile.benchmark)
        try:
            provider = get_provider(provider_name)
            panel = provider.fetch_panel(fetch_tickers, _lookback_days(profile, holdings))
        except ImportError:
            return None, [
                f'error: the {provider_name!r} provider is not installed. '
                f'Run: pip install "kuroshio[{provider_name}]"'
            ]
        # ponytail: latest session only, and no sector_map for `us-leadership` (that
        # factor renormalizes away) — add --asof/--sector-map here when propose needs to
        # reproduce a `kuroshio screen` number exactly. See tasks/TODO.md T25/T30.
        if need_scores:
            challengers, auto_scored = _score_missing(
                holdings, challengers, profile, panel, swap_hurdle(ips, market)[0],
                universe=universe,
            )
        # the monitoring seam: prices enter here, never inside the allocator.
        prices, ma50, asof = monitor_inputs(panel)
        running_high, atr14, min_close = trail_inputs(panel, holdings)
        book_vol = compute_book_vol(panel, holdings)

    cards = propose(
        holdings, challengers, ips, market,
        verdicts=verdicts, swaps_this_week=swaps_this_week, themes=themes,
        auto_scored=auto_scored, prices=prices, ma50=ma50, asof=asof,
        pool_name=pool_name, book_vol=book_vol,
        running_high=running_high, atr14=atr14, min_close=min_close,
        last_stop=_logged_stops(holdings, asof),
    )
    _log_ratchets(cards, market, asof)
    return cards, None


def _lookback_days(profile, holdings: list[Holding]) -> int:
    """The fetch window: the profile's, extended to reach the oldest ``entry_date`` in the
    book plus the profile's own window as warm-up (MA50 and ATR14 need sessions *before*
    the entry). Without this, ``signals.trail_inputs`` measures "since entry_date" over
    whatever the provider's default lookback happened to cover — 120 sessions for `tw` —
    and a drawdown older than that is never seen (it drops the ticker instead)."""
    entries = [h.entry_date for h in holdings if h.entry_date]
    if not entries:
        return profile.lookback_days
    try:
        held = (datetime.date.today() - datetime.date.fromisoformat(min(entries))).days
    except ValueError:   # a non-ISO entry_date is the holdings file's problem, not a crash
        return profile.lookback_days
    return max(profile.lookback_days, held + profile.lookback_days)


def _logged_stops(holdings: list[Holding], asof: str | None) -> dict[str, float]:
    """The newest ``STOPS`` level per held ticker, so this run's ratchet compares against
    the stop the last one logged rather than the level recorded in the holdings file — a
    trail that has since widened must not walk the stop back down, and a level that has
    not moved must not be logged again. Best-effort: an unreadable ledger warns."""
    from kuroshio.core import ledger

    date = asof or datetime.date.today().isoformat()
    try:
        rows = ledger.load(ledger.ledger_dir() / ledger.STOPS)
    except OSError as exc:
        print(f"warning: stop ledger read failed: {exc}", file=sys.stderr)
        return {}
    stops = {}
    for h in holdings:
        level = ledger.live_stop(rows, h.ticker, date)
        if level is not None:
            stops[h.ticker] = level
    return stops


def _log_ratchets(cards, market: str, asof: str | None) -> None:
    """Append every stop this run's ratchet moved to the ledger's ``STOPS`` file.

    A trailing stop is a level that moves, so a record of only the final one cannot say
    what was live when a rating was made — ``evaluate`` reads these rows back per date
    (``ledger.live_stop``). Best-effort, like the ``research`` rating append: an
    unwritable ledger warns and never costs the user their cards.
    """
    from kuroshio.core import ledger

    rows = [
        {
            "date": c.details.get("asof") or asof or datetime.date.today().isoformat(),
            "market": market,
            "ticker": c.details["ticker"],
            "old": c.details["old_invalidation"],
            "new": c.details["new_invalidation"],
            "reason": f"{c.details['setup_type']} atr trail",
        }
        for c in cards or [] if c.details.get("ratchet")
    ]
    if not rows:
        return
    try:
        path = ledger.ledger_dir() / ledger.STOPS
        ledger.append(path, rows)
        print(f"ledger: {len(rows)} stop move(s) -> {path}", file=sys.stderr)
    except OSError as exc:
        print(f"warning: stop ledger append failed: {exc}", file=sys.stderr)


def cmd_propose(args: argparse.Namespace) -> int:
    cards, problems = _run_propose(
        args.ips, args.holdings, args.market,
        candidates_path=args.candidates, universe_file=args.universe_file,
        swaps_this_week=args.swaps_this_week, provider_name=args.provider,
    )
    if problems is not None:
        # IPS validate() problems are plain (stdout, no prefix, ips-validate style);
        # a file/provider problem is "error: ..." (stderr) — see _run_propose.
        for p in problems:
            print(p, file=sys.stderr if p.startswith("error:") else sys.stdout)
        return 2

    if not cards:
        print("No proposals — portfolio is within policy.")
    else:
        print("\n\n".join(card.to_markdown() for card in cards))

    if args.discord_webhook and cards:
        from kuroshio.integrations.discord import post_cards

        ok = post_cards(args.discord_webhook, cards)
        print("posted proposals to Discord" if ok else "warning: Discord post failed", file=sys.stderr)

    return 0


# --- ips-validate ----------------------------------------------------------


def cmd_ips_validate(args: argparse.Namespace) -> int:
    from kuroshio.core.ips import parse_ips, validate

    ips = parse_ips(args.path)
    problems = validate(ips)
    if problems:
        for p in problems:
            print(p)
        return 2
    print(f"OK — valid IPS (risk_profile={ips.risk_profile}, markets={','.join(ips.universe.markets)})")
    return 0


# --- research ----------------------------------------------------------------


def cmd_research(args: argparse.Namespace) -> int:
    import copy

    try:
        from kuroshio.agents.engine.default_config import DEFAULT_CONFIG
        from kuroshio.agents.engine.graph.trading_graph import TradingAgentsGraph
    except ImportError:
        print(
            'error: the LLM research engine is not installed. Run: pip install "kuroshio[agents]" '
            "and set an LLM API key env var (e.g. OPENAI_API_KEY).",
            file=sys.stderr,
        )
        return 2

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["market_region"] = args.market
    config["output_lang"] = args.lang
    trade_date = args.date or datetime.date.today().isoformat()
    analysts = (
        [a.strip() for a in args.analysts.split(",") if a.strip()]
        if args.analysts
        else list(config[f"default_{args.market}_analysts"])
    )

    seed_reports: dict[str, str] = {}
    selected = analysts
    if not args.no_cache:
        from kuroshio.agents.engine.graph.facet_cache import plan_facets, write_back

        selected, seed_reports = plan_facets(
            facets_dir=config["facets_dir"],
            ticker=args.ticker,
            trade_date=trade_date,
            available_facets=analysts,
            ttl_days=int(config.get("fundamentals_ttl_days", 7)),
        )

    graph = TradingAgentsGraph(selected_analysts=selected, config=config)
    final_state, decision = graph.propagate(args.ticker, trade_date, seed_reports=seed_reports)

    if not args.no_cache:
        write_back(
            facets_dir=config["facets_dir"],
            ticker=args.ticker,
            trade_date=trade_date,
            lang=config.get("output_lang", "en"),
            regenerated_facets=selected,
            final_state=final_state,
        )

    save_path = Path(args.out) / args.ticker / trade_date
    report_path = graph.save_reports(final_state, args.ticker, save_path=save_path)
    print(f"report: {report_path}")
    if decision:
        print(f"verdict: {decision}")

    # stop_loss/price_target come off the same structured risk_controls the vendored
    # engine already produced for the strategy payload — computed once, ahead of the
    # --no-ledger gate, since the decision.json sidecar below needs it either way.
    controls = (final_state.get("strategy_payload") or {}).get("risk_controls") or {}

    if not args.no_ledger:
        try:
            from kuroshio.core import ledger

            row = {
                "date": trade_date, "market": args.market, "ticker": args.ticker,
                "rating": decision, "stop_loss": controls.get("stop_loss"),
                "price_target": controls.get("price_target"), "close": None,
            }
            path = ledger.ledger_dir() / ledger.RATINGS
            ledger.append(path, [row])
            print(f"ledger: 1 row -> {path}", file=sys.stderr)
        except Exception as exc:
            print(f"warning: ledger append failed: {exc}", file=sys.stderr)

    _write_decision_json(
        save_path, ticker=args.ticker, date=trade_date, market=args.market,
        rating=decision, stop_loss=controls.get("stop_loss"),
        price_target=controls.get("price_target"),
    )
    return 0


# A zh-TW run whose PM decision falls back to free text uses config/i18n/zh-TW.yaml's
# localized section labels instead of the English ones — the same two-locale problem
# the vendored writer's _LEVEL_LABELS solves for stop_loss/price_target (not reusable
# here: that table doesn't cover the prose fields), so cli.py carries its own pair.
_PROSE_FIELD_LABELS = {
    "executive_summary": ("Executive Summary", "執行摘要"),
    "investment_thesis": ("Investment Thesis", "投資論述"),
}


def _extract_prose_field(text: str, field: str) -> str | None:
    """Section text for `field`, trying the English label then the zh-TW label."""
    # reuse the vendored engine's labelled-section extractor rather than a second
    # regex over the same markdown (kuroshio/agents/engine/payloads/writer.py).
    from kuroshio.agents.engine.payloads.writer import _extract_markdown_field

    for label in _PROSE_FIELD_LABELS[field]:
        value = _extract_markdown_field(text, label)
        if value is not None:
            return value
    return None


def _write_decision_json(
    save_path: Path, *, ticker: str, date: str, market: str,
    rating: str | None, stop_loss: float | None, price_target: float | None,
) -> None:
    """Sidecar for `5_portfolio/decision.md` (TASK-18): the same rating/stop/target the
    ratings ledger carries, plus the prose the desk turns into a thesis card. A no-op
    when decision.md was never written (no PM judge_decision this run) — written even
    with --no-ledger, since the ledger and the sidecar answer different questions."""
    decision_md = save_path / "5_portfolio" / "decision.md"
    if not decision_md.exists():
        return
    text = decision_md.read_text(encoding="utf-8")
    fields = {name: _extract_prose_field(text, name) for name in _PROSE_FIELD_LABELS}
    missing = [name for name, value in fields.items() if value is None]
    if missing:
        print(
            f"research: decision.json {', '.join(missing)} null — no English or "
            "zh-TW label matched in decision.md",
            file=sys.stderr,
        )
    executive_summary, investment_thesis = fields["executive_summary"], fields["investment_thesis"]
    row = {
        "ticker": ticker, "date": date, "market": market, "rating": rating,
        "stop_loss": stop_loss, "price_target": price_target, "close": None,
        "executive_summary": executive_summary,
        "investment_thesis": investment_thesis,
        "source": None, "model": None,
    }
    (save_path / "5_portfolio" / "decision.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --- mcp -----------------------------------------------------------------------


def cmd_mcp(args: argparse.Namespace) -> int:
    # `from kuroshio.mcp_server import run` (not `from kuroshio import mcp_server`):
    # a dotted from-import always resolves the full module path through
    # sys.modules, so a test that monkeypatches sys.modules["kuroshio.mcp_server"]
    # to None reliably raises ImportError here — a bare `from kuroshio import X`
    # can short-circuit via getattr(kuroshio, "X") if X was already imported
    # elsewhere in the process (see tests/test_cli.py::test_mcp_missing_extra_exits_2).
    try:
        from kuroshio.mcp_server import run
    except ImportError:
        print(
            'error: the MCP server needs the mcp extra. Run: pip install "kuroshio[mcp]"',
            file=sys.stderr,
        )
        return 2
    run()
    return 0


# --- evaluate ------------------------------------------------------------------


def cmd_evaluate(args: argparse.Namespace) -> int:
    from kuroshio.core import ledger
    from kuroshio.providers import get_provider

    market = args.market
    profile = get_profile(market)
    ledger_dir_path = Path(args.ledger_dir) if args.ledger_dir else ledger.ledger_dir()
    print(f"ledger dir: {ledger_dir_path}", file=sys.stderr)

    scores = [r for r in ledger.load(ledger_dir_path / ledger.SCORES) if r.get("market") == market]
    ratings = [r for r in ledger.load(ledger_dir_path / ledger.RATINGS) if r.get("market") == market]
    stops = [r for r in ledger.load(ledger_dir_path / ledger.STOPS) if r.get("market") == market]

    dates = sorted({r["date"] for r in scores})
    if len(dates) < 2:
        print(f"evaluate: {len(dates)} run(s) logged; need at least 2 dates with a resolved horizon")
        return 0

    tickers = sorted({r["ticker"] for r in scores} | {r["ticker"] for r in ratings})
    if profile.benchmark:  # first: providers/yf.py filters the panel to its first resolved ticker
        tickers = [profile.benchmark] + [t for t in tickers if t != profile.benchmark]

    earliest = datetime.date.fromisoformat(dates[0])
    lookback_days = (datetime.date.today() - earliest).days + args.horizon * 2 + 10

    try:
        provider = get_provider(profile.default_provider)
        panel = provider.fetch_panel(tickers, lookback_days)
    except ImportError:
        print(
            f'error: the {profile.default_provider!r} provider is not installed. '
            f'Run: pip install "kuroshio[{profile.default_provider}]"',
            file=sys.stderr,
        )
        return 2

    summary = ledger.realized(scores, panel.close, args.horizon, profile.benchmark, args.top)
    rating_stats = ledger.rating_table(
        ratings, panel.close, args.horizon, by_source=True, stop_rows=stops
    )
    print(ledger.to_markdown(summary, rating_stats))
    return 0


# --- book / site -----------------------------------------------------------------


def _price_columns(book, provider_name: str):
    """(ma50 strings, book vol, window) for the book's names — only when --provider is given,
    so the default run touches no network and those columns say n/a."""
    from kuroshio.core.allocator.signals import BOOK_VOL_WINDOW
    from kuroshio.core.allocator.signals import book_vol as compute_book_vol
    from kuroshio.providers import get_provider

    holdings = [
        Holding(ticker=x["ticker"], weight=x["weight"], theme=x.get("theme", x["industry"]))
        for x in book["core"] + book["attack"]
    ]
    panel = get_provider(provider_name).fetch_panel(
        [h.ticker for h in holdings], 90, end=book["asof"]
    )
    close = panel.close
    ma50 = close.rolling(50).mean()
    out = {}
    for t in close.columns:
        last, avg = close[t].dropna(), ma50[t].dropna()
        if len(last) and len(avg):
            out[t] = f"{float(last.iloc[-1]) / float(avg.iloc[-1]) - 1:+.0%}"
    vol = compute_book_vol(panel, holdings)
    return out, vol, BOOK_VOL_WINDOW


def cmd_book(args: argparse.Namespace) -> int:
    from kuroshio.core import book as bookmod
    from kuroshio.core.ips import parse_ips

    rules = bookmod.BookRules(
        core_n=args.core_n, core_per_theme=args.core_per_theme, attack_n=args.attack_n,
        base_pct=args.base_pct, attack_budget_pct=args.attack_budget_pct,
        ttl_days=args.ttl_days, review_days=args.review_days,
        earnings_warn_days=args.earnings_warn_days,
    )
    try:
        book = bookmod.build_book(
            bookmod.load_screen(args.screen),
            bookmod.load_jsonl(args.ratings),
            parse_ips(args.ips),
            meta=bookmod.load_json(args.meta),
            scores_rows=bookmod.load_jsonl(args.scores),
            positions=bookmod.load_positions(args.positions),
            nav=args.nav,
            pm_size=bookmod.load_json(args.pm_size),
            locked=bookmod.load_json(args.locked),
            market=args.market,
            rules=rules,
            ips_name=Path(args.ips).name,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    holdings_path = out / "holdings.yml"
    holdings_path.write_text(bookmod.holdings_yaml(book), encoding="utf-8")

    # the same code path `kuroshio propose` takes, in-process — a propose that cannot run
    # (no provider, no network) is written to propose.out rather than losing the whole book.
    try:
        cards, problems = _run_propose(
            args.ips, str(holdings_path), args.market,
            universe_file=args.universe_file, provider_name=args.provider,
        )
        if problems is not None:
            propose_text = "\n".join(problems)
        else:
            propose_text = "\n\n".join(c.to_markdown() for c in cards) if cards else ""
    except Exception as exc:  # noqa: BLE001 — a failed propose must not lose the book
        propose_text = f"propose failed: {exc}"
        print(f"warning: propose failed: {exc}", file=sys.stderr)

    ma50, vol, window = {}, None, None
    if args.provider:
        try:
            ma50, vol, window = _price_columns(book, args.provider)
        except Exception as exc:  # noqa: BLE001 — the price columns are decoration
            print(f"warning: price panel unavailable: {exc}", file=sys.stderr)

    bookmod.write_book(
        book, out, propose_text=propose_text, lang=args.lang,
        ma50=ma50, book_vol=vol, vol_window=window,
    )
    print(
        f"{book['asof']}: core {len(book['core'])} · attack {len(book['attack'])} · "
        f"skipped {len(book['skipped'])} · gross {book['gross']:.1%} -> {out}"
    )
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from kuroshio.site.render import render_site

    try:
        pages = render_site(args.book, args.reports, args.out, lang=args.lang)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"site: {len(pages)} page(s) -> {Path(args.out) / 'index.html'}")
    return 0


# --- entry point -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kuroshio")
    sub = parser.add_subparsers(dest="command", required=True)

    p_screen = sub.add_parser("screen", help="rank breakout candidates in a market")
    p_screen.add_argument("--market", choices=sorted(PROFILES), required=True)
    p_screen.add_argument("--provider")
    tickers_group = p_screen.add_mutually_exclusive_group(required=True)
    tickers_group.add_argument("--tickers", help="comma-separated ticker list")
    tickers_group.add_argument("--tickers-file", help="newline-separated file, '#' comments allowed")
    p_screen.add_argument("--top", type=int, default=20)
    p_screen.add_argument("--asof", help="YYYY-MM-DD, default: latest session")
    p_screen.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us-leadership only)")
    p_screen.add_argument(
        "--no-gate", action="store_true",
        help="score every requested ticker without the Stage-1 breakout gate (Fix 2 — incumbent scoring)",
    )
    p_screen.add_argument(
        "--json", action="store_true", help="machine-readable JSON output instead of the text table"
    )
    p_screen.add_argument(
        "--no-ledger", action="store_true", help="skip appending score rows to the ledger"
    )
    p_screen.add_argument(
        "--snapshot-top", type=int, default=50,
        help="fetch a fundamentals snapshot only for the top N screened names "
        "(default 50; about 3 s per name)",
    )
    p_screen.set_defaults(func=cmd_screen)

    p_backtest = sub.add_parser(
        "backtest", help="walk-forward check: does final_score predict forward returns"
    )
    p_backtest.add_argument("--market", choices=sorted(PROFILES), required=True)
    p_backtest.add_argument("--provider")
    bt_tickers_group = p_backtest.add_mutually_exclusive_group(required=True)
    bt_tickers_group.add_argument("--tickers", help="comma-separated ticker list")
    bt_tickers_group.add_argument("--tickers-file", help="newline-separated file, '#' comments allowed")
    bt_tickers_group.add_argument(
        "--members-file",
        help="CSV of date,tickers snapshots (scripts/sp500_members.py); point-in-time universe",
    )
    p_backtest.add_argument("--weeks", type=int, default=52)
    p_backtest.add_argument("--horizon", type=int, default=20)
    p_backtest.add_argument("--top", type=int, default=10)
    p_backtest.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us-leadership only)")
    p_backtest.set_defaults(func=cmd_backtest)

    p_simulate = sub.add_parser(
        "simulate",
        help="walk-forward simulation: run the allocator (sizing/swap/trim/MAE), not just the score",
    )
    p_simulate.add_argument("--market", choices=sorted(PROFILES), required=True)
    p_simulate.add_argument("--ips", required=True)
    p_simulate.add_argument("--provider")
    sim_tickers_group = p_simulate.add_mutually_exclusive_group(required=True)
    sim_tickers_group.add_argument("--tickers", help="comma-separated ticker list")
    sim_tickers_group.add_argument("--tickers-file", help="newline-separated file, '#' comments allowed")
    sim_tickers_group.add_argument(
        "--members-file",
        help="CSV of date,tickers snapshots (scripts/sp500_members.py); point-in-time universe",
    )
    p_simulate.add_argument("--weeks", type=int, default=52)
    p_simulate.add_argument("--top", type=int, default=10)
    p_simulate.add_argument("--step", type=int, default=5)
    p_simulate.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us-leadership only)")
    p_simulate.set_defaults(func=cmd_simulate)

    p_propose = sub.add_parser("propose", help="propose portfolio swaps against an IPS")
    p_propose.add_argument("--ips", required=True)
    p_propose.add_argument("--holdings", required=True)
    p_propose.add_argument("--market", choices=sorted(PROFILES), required=True)
    p_propose.add_argument("--provider")
    p_propose.add_argument("--candidates")
    p_propose.add_argument(
        "--universe-file",
        help="cross-section for auto-filled scores: a newline ticker list, or a "
        "date,tickers snapshot (scripts/sp500_members.py) whose latest row is used. "
        "Without it, auto-filled scores are ranked against holdings+candidates only.",
    )
    p_propose.add_argument("--swaps-this-week", type=int, default=0)
    p_propose.add_argument(
        "--discord-webhook",
        default=os.getenv("KUROSHIO_DISCORD_WEBHOOK"),
        help="Discord webhook URL to post proposal cards to (default: env KUROSHIO_DISCORD_WEBHOOK)",
    )
    p_propose.set_defaults(func=cmd_propose)

    p_validate = sub.add_parser("ips-validate", help="validate an IPS markdown file")
    p_validate.add_argument("path")
    p_validate.set_defaults(func=cmd_ips_validate)

    p_research = sub.add_parser("research", help="run the LLM multi-agent research pipeline for one ticker")
    p_research.add_argument("ticker")
    p_research.add_argument("--market", choices=["us", "tw"], default="us")
    p_research.add_argument("--date", help="YYYY-MM-DD, default: today")
    p_research.add_argument("--lang", choices=["en", "zh-TW"], default="en")
    p_research.add_argument(
        "--analysts", help="comma-separated analyst keys, default: the market's full set"
    )
    p_research.add_argument(
        "--no-cache", action="store_true", help="bypass the facet cache; run every analyst"
    )
    p_research.add_argument("--out", default="./reports", help="report output directory (default: ./reports)")
    p_research.add_argument(
        "--no-ledger", action="store_true", help="skip appending a rating row to the ledger"
    )
    p_research.set_defaults(func=cmd_research)

    p_evaluate = sub.add_parser(
        "evaluate", help="read the score/rating ledger and print realized forward performance"
    )
    p_evaluate.add_argument("--market", choices=sorted(PROFILES), required=True)
    p_evaluate.add_argument("--horizon", type=int, default=20)
    p_evaluate.add_argument("--top", type=int, default=10)
    p_evaluate.add_argument(
        "--ledger-dir", help="override $KUROSHIO_LEDGER_DIR / ~/.kuroshio/ledger for this run"
    )
    p_evaluate.set_defaults(func=cmd_evaluate)

    p_book = sub.add_parser(
        "book", help="build a mechanical book from a screen, ratings and an IPS (no network by default)"
    )
    p_book.add_argument("--screen", required=True, help="`kuroshio screen --json` output")
    p_book.add_argument("--ratings", required=True, help="ratings ledger (JSONL, newest wins)")
    p_book.add_argument("--ips", required=True)
    p_book.add_argument("--out", required=True, help="output directory (created if missing)")
    p_book.add_argument("--market", choices=sorted(PROFILES), default="us")
    p_book.add_argument(
        "--scores", help="scores ledger (JSONL); adds the earnings expiry to the rating TTL"
    )
    p_book.add_argument("--meta", help="JSON of {ticker: {sector, industry, vol}} for the theme cap")
    p_book.add_argument("--nav", type=float, help="account NAV the dollar allocation is sized on")
    p_book.add_argument(
        "--positions",
        help="symbol,quantity,market_value,average_price[,asset_type] table (CSV or JSON)",
    )
    p_book.add_argument("--pm-size", help="JSON of {ticker: multiplier} to size a name down")
    p_book.add_argument("--locked", help="JSON of {ticker: {theme, note}} the book must not resize")
    p_book.add_argument("--universe-file", help="cross-section for propose's auto-filled scores")
    p_book.add_argument(
        "--provider", help="price provider for the MA50 and book-vol columns (default: no fetch)"
    )
    p_book.add_argument("--lang", help="label language; default: the IPS `lang` field")
    p_book.add_argument("--core-n", type=int, default=15)
    p_book.add_argument("--core-per-theme", type=int, default=3)
    p_book.add_argument("--attack-n", type=int, default=3)
    p_book.add_argument("--base-pct", type=float, default=5.0)
    p_book.add_argument("--attack-budget-pct", type=float, default=15.0)
    p_book.add_argument("--ttl-days", type=int, default=45)
    p_book.add_argument("--review-days", type=int, default=21)
    p_book.add_argument("--earnings-warn-days", type=int, default=7)
    p_book.set_defaults(func=cmd_book)

    p_site = sub.add_parser("site", help="render a book directory as a static site")
    p_site.add_argument("--book", required=True, help="a `kuroshio book --out` directory")
    p_site.add_argument("--reports", help="a `kuroshio research --out` tree (<TICKER>/<date>/)")
    p_site.add_argument("--out", required=True, help="output directory (swapped in atomically)")
    p_site.add_argument("--lang", help="default: the book's IPS `lang` field; unknown -> en")
    p_site.set_defaults(func=cmd_site)

    p_mcp = sub.add_parser(
        "mcp", help="run a stdio MCP server exposing the engine's dataflows for a Claude Code session"
    )
    p_mcp.set_defaults(func=cmd_mcp)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
