"""kuroshio CLI — screen | propose | ips-validate.

Stdlib argparse only (no click/typer/rich). Providers and yaml are imported
lazily inside each command so ``kuroshio --help`` stays fast and never
touches the network. Network calls happen only in the ``screen`` command.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from kuroshio.types import Candidate, Holding

# ponytail: lookback derived from each profile's longest MA window + margin
# (US MA200 needs ~200 trading sessions -> 320 calendar days; TW MA60 needs
# ~60 trading sessions -> 120 calendar days). Hardcoded, not computed from
# the profile modules, to keep the CLI decoupled from their internals.
LOOKBACK_DAYS = {"us": 320, "tw": 120}
DEFAULT_PROVIDER = {"us": "yfinance", "tw": "finmind"}


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
    return [Holding(**item) for item in _load_yaml(path)]


def _candidates_from_yaml(path: str) -> tuple[list[Candidate], dict[str, str], dict[str, str]]:
    today = datetime.date.today().isoformat()
    candidates: list[Candidate] = []
    verdicts: dict[str, str] = {}
    themes: dict[str, str] = {}
    for item in _load_yaml(path):
        ticker = item["ticker"]
        if item.get("verdict") is not None:
            verdicts[ticker] = item["verdict"]
        if item.get("theme") is not None:
            themes[ticker] = item["theme"]
        candidates.append(Candidate(ticker=ticker, date=today, rank=0, final_score=item["final_score"]))
    return candidates, verdicts, themes


# --- screen ------------------------------------------------------------------


def _print_screen_table(market: str, candidates: list[Candidate]) -> None:
    asof = candidates[0].date if candidates else "n/a"
    print(f"market={market} asof={asof} candidates={len(candidates)}")
    if market == "tw" and candidates and candidates[0].flags.get("degraded"):
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
    line = lambda cells: "  ".join(cell.ljust(w) for cell, w in zip(cells, widths))
    print(line(headers))
    for row in rows:
        print(line(row))


def cmd_screen(args: argparse.Namespace) -> int:
    import yaml

    from kuroshio.providers import get_provider

    market = args.market
    provider_name = args.provider or DEFAULT_PROVIDER[market]
    tickers = _parse_tickers(args.tickers, args.tickers_file)
    if not tickers:
        print("error: --tickers / --tickers-file resolved to zero tickers", file=sys.stderr)
        return 2

    sector_map = None
    if args.sector_map:
        sector_map = yaml.safe_load(Path(args.sector_map).read_text()) or {}

    fetch_tickers = list(tickers)
    if market == "us":
        extra = {"SPY"} | (set(sector_map.values()) if sector_map else set())
        fetch_tickers += [t for t in extra if t not in fetch_tickers]

    provider = get_provider(provider_name)
    panel = provider.fetch_panel(fetch_tickers, LOOKBACK_DAYS[market], end=args.asof)

    if market == "us":
        from kuroshio.core.screening.us import screen

        candidates = screen(panel, asof=args.asof, sector_map=sector_map)
    else:
        from kuroshio.core.screening.tw import screen

        candidates = screen(panel, asof=args.asof)

    _print_screen_table(market, candidates[: args.top])
    return 0


# --- propose -------------------------------------------------------------


def cmd_propose(args: argparse.Namespace) -> int:
    from kuroshio.core.allocator import propose
    from kuroshio.core.ips import parse_ips, validate

    ips = parse_ips(args.ips)
    problems = validate(ips)
    if problems:
        for p in problems:
            print(p)
        return 2

    holdings = _holdings_from_yaml(args.holdings)
    challengers, verdicts, themes = [], {}, {}
    if args.candidates:
        challengers, verdicts, themes = _candidates_from_yaml(args.candidates)

    cards = propose(
        holdings, challengers, ips, args.market,
        verdicts=verdicts, swaps_this_week=args.swaps_this_week, themes=themes,
    )

    if not cards:
        print("No proposals — portfolio is within policy.")
    else:
        print("\n\n".join(card.to_markdown() for card in cards))
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


# --- entry point -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kuroshio")
    sub = parser.add_subparsers(dest="command", required=True)

    p_screen = sub.add_parser("screen", help="rank breakout candidates in a market")
    p_screen.add_argument("--market", choices=["us", "tw"], required=True)
    p_screen.add_argument("--provider")
    tickers_group = p_screen.add_mutually_exclusive_group(required=True)
    tickers_group.add_argument("--tickers", help="comma-separated ticker list")
    tickers_group.add_argument("--tickers-file", help="newline-separated file, '#' comments allowed")
    p_screen.add_argument("--top", type=int, default=20)
    p_screen.add_argument("--asof", help="YYYY-MM-DD, default: latest session")
    p_screen.add_argument("--sector-map", help="YAML file of {ticker: sector_etf} (us only)")
    p_screen.set_defaults(func=cmd_screen)

    p_propose = sub.add_parser("propose", help="propose portfolio swaps against an IPS")
    p_propose.add_argument("--ips", required=True)
    p_propose.add_argument("--holdings", required=True)
    p_propose.add_argument("--market", choices=["us", "tw"], required=True)
    p_propose.add_argument("--candidates")
    p_propose.add_argument("--swaps-this-week", type=int, default=0)
    p_propose.set_defaults(func=cmd_propose)

    p_validate = sub.add_parser("ips-validate", help="validate an IPS markdown file")
    p_validate.add_argument("path")
    p_validate.set_defaults(func=cmd_ips_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
