#!/usr/bin/env python3
"""Reconstruct point-in-time S&P 500 membership from Wikipedia — one CSV row per change date.

Usage: python scripts/sp500_members.py OUT.csv [--since 2020-01-01] [--oldid REVID]

Walks the "Selected changes" table backwards from today's constituent list: before
each change's effective date, the added ticker was not a member and the removed one
was. Output columns: ``date`` (ISO) and ``tickers`` (space-separated, yfinance
spelling — ``BRK-B`` not ``BRK.B``), ascending; the first row is the membership on
``--since``. Feed it to ``kuroshio simulate --members-file``.

Needs ``lxml`` (pandas.read_html). Network: two Wikipedia page reads, nothing else.

Caveats the output carries, not fixes: the live page dropped the changes table in
2026, so ``--oldid`` defaults to the last revision that still had it (2026-05-23,
changes through 2026-05-07) — membership after that date is today's list; ticker
renames (FB→META) are not tracked, so a renamed name may be absent under its old
symbol; delisted names may have no price history left at the provider, which is
the residual survivorship bias ``simulate`` cannot remove.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request

import pandas as pd

PAGE = "List_of_S%26P_500_companies"
LAST_REV_WITH_CHANGES = 1355685534
UA = {"User-Agent": "kuroshio/0.1 (https://github.com/HaoweiChan/kuroshio)"}


def _html(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()


def _sym(s: object) -> str | None:
    if not isinstance(s, str) or not s.strip():
        return None
    return s.strip().upper().replace(".", "-")


def _tables(html: str) -> list[pd.DataFrame]:
    tabs = pd.read_html(io.StringIO(html))
    for t in tabs:
        t.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
    return tabs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--oldid", type=int, default=LAST_REV_WITH_CHANGES)
    args = ap.parse_args(argv)

    current = _tables(_html(f"https://en.wikipedia.org/wiki/{PAGE}"))[0]
    members = {_sym(s) for s in current["Symbol"]} - {None}

    old = _tables(_html(f"https://en.wikipedia.org/w/index.php?title={PAGE}&oldid={args.oldid}"))
    changes = next(
        t for t in old if any("Added" in c for c in t.columns) and any("Removed" in c for c in t.columns)
    )
    date_col = changes.columns[0]
    added_col = next(c for c in changes.columns if c.startswith("Added") and "Ticker" in c)
    removed_col = next(c for c in changes.columns if c.startswith("Removed") and "Ticker" in c)
    changes = changes.assign(_date=pd.to_datetime(changes[date_col], format="mixed", errors="coerce"))
    changes = changes.dropna(subset=["_date"]).sort_values("_date", ascending=False)

    # walk back: state after each change date is `members`; before it, undo the change.
    snapshots: dict[str, set[str]] = {}
    for _, row in changes.iterrows():
        day = row["_date"].date().isoformat()
        snapshots.setdefault(day, set(members))
        if (a := _sym(row[added_col])) is not None:
            members.discard(a)
        if (r := _sym(row[removed_col])) is not None:
            members.add(r)
        if day <= args.since:
            break
    snapshots[args.since] = set(members)

    rows = sorted((d, s) for d, s in snapshots.items() if d >= args.since)
    pd.DataFrame(
        {"date": [d for d, _ in rows], "tickers": [" ".join(sorted(s)) for _, s in rows]}
    ).to_csv(args.out, index=False)
    union = set().union(*(s for _, s in rows))
    print(
        f"{len(rows)} snapshots {rows[0][0]} -> {rows[-1][0]}, {len(union)} distinct tickers",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
