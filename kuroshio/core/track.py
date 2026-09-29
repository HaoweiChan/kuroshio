"""The book's own track record: what the names it recommended did, on price alone.

Raw returns, not NAV. Each saved book (`<root>/<asof>/book.json`) is held from its `asof`
close until the next book replaces it; a day's return is the weight-averaged return of the
names in the book that day, normalised by their summed weight — so cash, locked positions
and the size of anyone's account never enter it. The same, per sleeve (core / attack), and
per name: an *episode* is a contiguous run of books that carried the name, entered at the
first book's close and exited at the close of the first book that dropped it.

Pure over a list of books and a close panel; `kuroshio book --provider` feeds it and writes
`track.json`, `kuroshio site` renders that file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def book_weights(book: dict) -> dict[str, dict]:
    """{ticker: {weight, sleeve}} — a core name topped up by the attack budget is attack."""
    out = {x["ticker"]: {"weight": x["weight"], "sleeve": x.get("sleeve", "core")} for x in book["core"]}
    out.update({x["ticker"]: {"weight": x["weight"], "sleeve": "attack"} for x in book["attack"]})
    return out


def load_books(root: Path, current: dict | None = None) -> list[tuple[str, dict]]:
    """(asof, weights) for every dated book dir under `root`, oldest first; `current` (the
    book being written, not yet moved into its dated dir) replaces a same-asof one."""
    books = {}
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if _DATE.match(d.name) and (d / "book.json").exists():
            b = json.loads((d / "book.json").read_text())
            books[b["asof"]] = book_weights(b)
    if current:
        books[current["asof"]] = book_weights(current)
    return sorted(books.items())


def _day(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def track(books: list[tuple[str, dict]], close: pd.DataFrame, benchmark: str | None = None) -> dict:
    """Cumulative raw return of the book, each sleeve and the benchmark, plus every episode."""
    close = close.sort_index()
    days = [_day(t) for t in close.index]
    series, cum = [], {"book": 1.0, "core": 1.0, "attack": 1.0, "bench": 1.0}
    k = -1  # index of the book in force at the previous close
    for i in range(1, len(days)):
        while k + 1 < len(books) and books[k + 1][0] <= days[i - 1]:
            k += 1
        if k < 0:
            continue
        ret = close.iloc[i] / close.iloc[i - 1] - 1
        for key in ("book", "core", "attack"):
            held = [(w["weight"], ret.get(t)) for t, w in books[k][1].items()
                    if key == "book" or w["sleeve"] == key]
            held = [(w, r) for w, r in held if r is not None and pd.notna(r)]
            if held:
                cum[key] *= 1 + sum(w * r for w, r in held) / sum(w for w, _ in held)
        if benchmark and pd.notna(ret.get(benchmark)):
            cum["bench"] *= 1 + ret[benchmark]
        series.append({"date": days[i], **{key: round(v - 1, 5) for key, v in cum.items()}})

    def px(ticker: str, day: str) -> float | None:
        if ticker not in close:
            return None
        s = close[ticker].dropna()
        s = s[[_day(t) <= day for t in s.index]]
        return float(s.iloc[-1]) if len(s) else None

    episodes, open_runs = [], {}
    for asof, weights in books:
        for t in [t for t in open_runs if t not in weights]:
            run = open_runs.pop(t)
            run.update(exit_date=asof, exit=px(t, asof), open=False)
            episodes.append(run)
        for t, w in weights.items():
            run = open_runs.setdefault(t, {"ticker": t, "entry_date": asof, "entry": px(t, asof),
                                           "sleeves": [], "books": 0})
            run["books"] += 1
            run["last_weight"] = w["weight"]
            if w["sleeve"] not in run["sleeves"]:
                run["sleeves"].append(w["sleeve"])
    last = days[-1] if days else None
    for t, run in open_runs.items():
        run.update(exit_date=last, exit=px(t, last) if last else None, open=True)
        episodes.append(run)
    for e in episodes:
        e["ret"] = round(e["exit"] / e["entry"] - 1, 5) if e["entry"] and e["exit"] else None

    return {
        "since": books[0][0] if books else None, "asof": last, "benchmark": benchmark,
        "books": len(books), "series": series, "episodes": episodes,
    }


def summary(tr: dict) -> dict:
    """Headline numbers the site shows: cumulative per line, and episode hit rates."""
    last = tr["series"][-1] if tr["series"] else {}
    out = {key: last.get(key) for key in ("book", "core", "attack", "bench")}
    for key in ("all", "core", "attack"):
        rets = [e["ret"] for e in tr["episodes"] if e["ret"] is not None
                and (key == "all" or key in e["sleeves"])]
        out[f"n_{key}"] = len(rets)
        out[f"hit_{key}"] = sum(r > 0 for r in rets) / len(rets) if rets else None
        out[f"avg_{key}"] = sum(rets) / len(rets) if rets else None
    return out
