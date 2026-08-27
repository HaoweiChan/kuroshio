"""kuroshio CLI — screen | backtest | propose | ips-validate | research.

Stdlib argparse only (no click/typer/rich). Providers and yaml are imported
lazily inside each command so ``kuroshio --help`` stays fast and never
touches the network. Network calls happen only in the ``screen``, ``backtest``,
``research`` and — when a score is missing from the input files — ``propose``.
``research`` additionally requires the optional ``agents`` extra (LLM engine)
and exits 2 with an install hint if it's missing.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import math
import os
import sys
from pathlib import Path

from kuroshio.core.screening import PROFILES, get_profile
from kuroshio.types import SETUP_TYPES, Candidate, Holding


def _parse_tickers(tickers: str | None, tickers_file: str | None) -> list[str]:
    if tickers_file:
        out = []
        for line in Path(tickers_file).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
        return out
    return [t.strip() for t in (tickers or "").split(",") if t.strip()]


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
    return 0


# --- backtest ------------------------------------------------------------


def cmd_backtest(args: argparse.Namespace) -> int:
    import yaml

    from kuroshio.core.backtest import walkforward
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
    result = walkforward(
        panel, profile.screen, horizon=args.horizon, top_k=args.top,
        benchmark=profile.benchmark, min_history=profile.min_history, **screen_kwargs,
    )

    print(result.to_markdown())
    print(
        "\ncaveat: the supplied tickers ARE the universe — passing only today's "
        "survivors introduces survivorship bias; point-in-time membership is on you."
    )
    return 0


# --- propose -------------------------------------------------------------


def _score_missing(
    holdings: list[Holding], challengers: list[Candidate], profile, panel, hurdle: float
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
    """
    names = list(dict.fromkeys([h.ticker for h in holdings] + [c.ticker for c in challengers]))
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


def cmd_propose(args: argparse.Namespace) -> int:
    from kuroshio.core.allocator import propose
    from kuroshio.core.allocator.engine import MONITORED_SETUPS, swap_hurdle
    from kuroshio.core.allocator.signals import monitor_inputs
    from kuroshio.core.ips import parse_ips, validate
    from kuroshio.providers import get_provider

    ips = parse_ips(args.ips)
    problems = validate(ips)
    if problems:
        for p in problems:
            print(p)
        return 2

    challengers, verdicts, themes, auto_scored = [], {}, {}, {}
    try:
        holdings = _holdings_from_yaml(args.holdings)
        if args.candidates:
            challengers, verdicts, themes = _candidates_from_yaml(args.candidates)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # The user is no longer the integration layer: anything without a hand-typed
    # score gets one from the screener, and a holding with a monitored setup_type gets
    # the prices its thesis rule reads. Neither needed -> no fetch, no network.
    prices: dict[str, float] = {}
    ma50: dict[str, float] = {}
    need_scores = any(h.score is None for h in holdings) or any(
        c.final_score is None for c in challengers
    )
    monitored = any(h.setup_type in MONITORED_SETUPS for h in holdings)
    if need_scores or monitored:
        profile = get_profile(args.market)
        provider_name = args.provider or profile.default_provider
        fetch_tickers = list(
            dict.fromkeys([h.ticker for h in holdings] + [c.ticker for c in challengers])
        )
        if profile.benchmark and profile.benchmark not in fetch_tickers:
            fetch_tickers.append(profile.benchmark)
        try:
            provider = get_provider(provider_name)
            panel = provider.fetch_panel(fetch_tickers, profile.lookback_days)
        except ImportError:
            print(
                f'error: the {provider_name!r} provider is not installed. '
                f'Run: pip install "kuroshio[{provider_name}]"',
                file=sys.stderr,
            )
            return 2
        # ponytail: latest session only, and no sector_map for `us` (that factor
        # renormalizes away) — add --asof/--sector-map here when propose needs to
        # reproduce a `kuroshio screen` number exactly. See tasks/TODO.md T25/T30.
        if need_scores:
            challengers, auto_scored = _score_missing(
                holdings, challengers, profile, panel, swap_hurdle(ips, args.market)[0]
            )
        # the monitoring seam: prices enter here, never inside the allocator.
        prices, ma50 = monitor_inputs(panel)

    cards = propose(
        holdings, challengers, ips, args.market,
        verdicts=verdicts, swaps_this_week=args.swaps_this_week, themes=themes,
        auto_scored=auto_scored, prices=prices, ma50=ma50,
    )

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
    p_screen.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us only)")
    p_screen.add_argument(
        "--no-gate", action="store_true",
        help="score every requested ticker without the Stage-1 breakout gate (Fix 2 — incumbent scoring)",
    )
    p_screen.add_argument(
        "--json", action="store_true", help="machine-readable JSON output instead of the text table"
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
    p_backtest.add_argument("--weeks", type=int, default=52)
    p_backtest.add_argument("--horizon", type=int, default=20)
    p_backtest.add_argument("--top", type=int, default=10)
    p_backtest.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us only)")
    p_backtest.set_defaults(func=cmd_backtest)

    p_propose = sub.add_parser("propose", help="propose portfolio swaps against an IPS")
    p_propose.add_argument("--ips", required=True)
    p_propose.add_argument("--holdings", required=True)
    p_propose.add_argument("--market", choices=["us", "tw"], required=True)
    p_propose.add_argument("--provider")
    p_propose.add_argument("--candidates")
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
    p_research.set_defaults(func=cmd_research)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
