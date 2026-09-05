"""Plain-file forward-performance ledger — the record ``kuroshio evaluate`` reads.

docs/backtest-2026-09.md found no price-only ranking that beats SPY, so the only
routes to a signal left are fundamentals/estimates and the qualitative (LLM) layer.
Both need a forward record from day one, before anyone knows whether they work —
hence a dumb, dependency-free JSONL append log rather than a DB.

Two files under ``ledger_dir()`` (default ``~/.kuroshio/ledger``, override with
``$KUROSHIO_LEDGER_DIR``), one JSON object per line:

``scores.jsonl`` (``SCORES``) — one row per candidate on a ``kuroshio screen`` run::

    {"date", "market", "profile", "ticker", "rank", "final_score", "scores",
     "factors", "close", "fundamentals"}

``fundamentals`` is ``None``, or a snapshot fetched only for the top N screened
names::

    {"forward_pe", "forward_eps", "trailing_eps", "trailing_pe",
     "market_cap", "sector", "industry", "eps_rev_up_30d", "eps_rev_down_30d",
     "eps_est_growth_fy", "n_analysts", "rec_buy", "rec_hold", "rec_sell",
     "next_earnings_date", "last_surprise_pct", "insider_net_shares_90d", "asof"}

with any key the provider didn't return set to ``None``; ``asof`` is the screen
run's date, not a fetch timestamp. ``forward_pe`` is yfinance's next-fiscal-year multiple
(see ``providers/yf.py:fetch_fundamentals``), so the earnings-yield IC in ``realized`` is on
``+1y`` earnings, not current-year.

``ratings.jsonl`` (``RATINGS``) — one row per ``kuroshio research`` run, or per
``record_rating`` call from a ``kuroshio mcp`` session::

    {"date", "market", "ticker", "rating", "stop_loss", "price_target", "close",
     "source", "model"}

``stop_loss``/``price_target``/``close`` are ``None`` when unavailable.
``source``/``model`` are ``None`` for the paid ``kuroshio research`` path (or
absent on rows written before TASK-10) and ``"claude-session"``/the session's
model id for a session-mode run — see ``rating_table(..., by_source=True)``.

``stops.jsonl`` (``STOPS``) — one row per stop the allocator's ratchet moved on a
``kuroshio propose`` run (TASK-11)::

    {"date", "market", "ticker", "old", "new", "reason"}

``old`` is ``None`` when the position had no invalidation price before the move.
A trailing stop is a moving level, so scoring a rating against the *final* one is
scoring a number that was not live when the rating was made — ``live_stop`` reads
back the level that was live on a given date, and ``rating_table`` uses it.

This module is pure file IO plus the realized-performance math (rank-IC, top-k
forward return, per-rating hit rate) — no provider imports, stdlib + pandas only.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

SCORES = "scores.jsonl"
RATINGS = "ratings.jsonl"
STOPS = "stops.jsonl"

logger = logging.getLogger(__name__)

# First-cut hit definitions (see rating_table docstring) — "buy"-family wants a
# positive forward return, "sell"-family a negative one, "hold" wants it to have
# stayed roughly flat. Matched case-insensitively against the rating string.
_HIT_RULES = {
    "buy": lambda fwd: fwd > 0,
    "overweight": lambda fwd: fwd > 0,
    "sell": lambda fwd: fwd < 0,
    "underweight": lambda fwd: fwd < 0,
    "hold": lambda fwd: abs(fwd) < 0.05,
}


def ledger_dir() -> Path:
    env = os.environ.get("KUROSHIO_LEDGER_DIR")
    return Path(env) if env else Path.home() / ".kuroshio" / "ledger"


def append(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def load(path: Path) -> list[dict]:
    """All rows in ``path``. Missing file -> []. A malformed line is skipped (with a
    warning naming the line number) rather than crashing the whole read."""
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("%s:%d: malformed JSONL line, skipped", path, lineno)
    return rows


def live_stop(stop_rows: list[dict], ticker: str, date: str) -> float | None:
    """The stop live for ``ticker`` on ``date``: the ``new`` level of the newest ratchet
    move at or before it. None when the ticker had not been ratcheted by then — the
    caller decides whether that means "no stop" or "the one recorded elsewhere"."""
    moves = [
        r for r in stop_rows
        if r.get("ticker") == ticker and r.get("new") is not None and str(r.get("date")) <= date
    ]
    return float(max(moves, key=lambda r: str(r["date"]))["new"]) if moves else None


def _positional_index(index: pd.Index, date: str) -> int | None:
    """Row of ``date`` in ``index``, or of the first session after it: a ``research``
    run dated on a weekend is measured from the next open, not dropped. None past the end."""
    loc = int(index.searchsorted(date))
    return loc if loc < len(index) else None


def realized(
    scores_rows: list[dict],
    close: pd.DataFrame,
    horizon: int,
    benchmark: str | None,
    top_k: int,
) -> dict:
    """Realized performance of logged scores against ``close``, one entry per score
    date that has a resolved forward horizon (a session >= ``horizon`` sessions
    later in ``close``'s index). Forward return is positional on that index —
    ``close[t + horizon] / close[t] - 1`` — never a calendar-day lookup."""
    by_date: dict[str, list[dict]] = {}
    for row in scores_rows:
        by_date.setdefault(row["date"], []).append(row)

    per_date = []
    for date in sorted(by_date):
        i = _positional_index(close.index, date)
        if i is None or i + horizon >= len(close.index):
            continue

        scored: list[tuple[dict, float]] = []
        for row in by_date[date]:
            ticker = row["ticker"]
            if ticker not in close.columns:
                continue
            c0, c1 = close[ticker].iloc[i], close[ticker].iloc[i + horizon]
            if pd.isna(c0) or pd.isna(c1):
                continue
            scored.append((row, float(c1 / c0 - 1.0)))
        if not scored:
            continue

        ic = None
        if len(scored) >= 3:
            pair = pd.DataFrame(
                {"score": [r["final_score"] for r, _ in scored], "fwd": [f for _, f in scored]}
            )
            ic = float(pair["score"].rank().corr(pair["fwd"].rank()))

        ranked = sorted(scored, key=lambda rf: rf[0]["rank"])[:top_k]
        topk_fwd = float(sum(f for _, f in ranked) / len(ranked))

        bench_fwd = None
        if benchmark and benchmark in close.columns:
            b0, b1 = close[benchmark].iloc[i], close[benchmark].iloc[i + horizon]
            if pd.notna(b0) and pd.notna(b1):
                bench_fwd = float(b1 / b0 - 1.0)

        ey_pairs = []
        for row, fwd in scored:
            fundamentals = row.get("fundamentals")
            fpe = fundamentals.get("forward_pe") if fundamentals else None
            if fpe is not None and fpe > 0:
                ey_pairs.append((1.0 / fpe, fwd))
        ey_ic = None
        if len(ey_pairs) >= 3:
            ey_df = pd.DataFrame(ey_pairs, columns=["ey", "fwd"])
            ey_ic = float(ey_df["ey"].rank().corr(ey_df["fwd"].rank()))

        rev_pairs = []
        for row, fwd in scored:
            fundamentals = row.get("fundamentals")
            up = fundamentals.get("eps_rev_up_30d") if fundamentals else None
            down = fundamentals.get("eps_rev_down_30d") if fundamentals else None
            if up is not None and down is not None and (up + down) > 0:
                rev_pairs.append(((up - down) / (up + down), fwd))
        rev_ic = None
        if len(rev_pairs) >= 3:
            rev_df = pd.DataFrame(rev_pairs, columns=["breadth", "fwd"])
            rev_ic = float(rev_df["breadth"].rank().corr(rev_df["fwd"].rank()))

        per_date.append({
            "date": date, "n": len(scored), "ic": ic, "topk_fwd": topk_fwd,
            "bench_fwd": bench_fwd, "ey_ic": ey_ic, "rev_ic": rev_ic,
        })

    if not per_date:
        return {
            "per_date": [], "mean_ic": None, "mean_topk_fwd": None, "mean_excess": None,
            "beat_rate": None, "mean_ey_ic": None, "mean_rev_ic": None, "n_dates": 0,
        }

    df = pd.DataFrame(per_date)
    ic_s = df["ic"].dropna()
    topk_s = df["topk_fwd"].dropna()
    ey_s = df["ey_ic"].dropna()
    rev_s = df["rev_ic"].dropna()
    both = df.dropna(subset=["topk_fwd", "bench_fwd"])
    mean_excess = beat_rate = None
    if not both.empty:
        excess = both["topk_fwd"] - both["bench_fwd"]
        mean_excess = float(excess.mean())
        beat_rate = float((excess > 0).mean())

    return {
        "per_date": per_date,
        "mean_ic": float(ic_s.mean()) if not ic_s.empty else None,
        "mean_topk_fwd": float(topk_s.mean()) if not topk_s.empty else None,
        "mean_excess": mean_excess,
        "beat_rate": beat_rate,
        "mean_ey_ic": float(ey_s.mean()) if not ey_s.empty else None,
        "mean_rev_ic": float(rev_s.mean()) if not rev_s.empty else None,
        "n_dates": len(per_date),
    }


def rating_table(
    rating_rows: list[dict], close: pd.DataFrame, horizon: int, by_source: bool = False,
    stop_rows: list[dict] | None = None,
) -> dict[str, dict]:
    """Per-rating {n, mean_fwd, hit_rate} off logged ratings vs. realized forward return.

    Hit is a first cut, not a calibrated definition: Buy/Overweight hits on a
    positive forward return, Sell/Underweight on a negative one, Hold on staying
    within +-5%. A rating not in that vocabulary gets n/mean_fwd but hit_rate=None.

    ``by_source``: when True and more than one distinct ``source`` appears among
    ``rating_rows`` (e.g. ``kuroshio research``'s paid path vs. a session's
    ``claude-session``), each rating's bucket is split by source — key becomes
    ``"<rating> (<source>)"`` — so a cheap-tier/heavy-tier hit-rate gap is visible.
    A single source, or by_source=False, groups exactly as before.

    ``stop_rows``: the ``STOPS`` ledger. Given it, each rated position is also scored
    against the stop that was **live on its own rating date** — the newest ratchet move
    at or before it, falling back to the row's recorded ``stop_loss`` — and the bucket
    gains ``n_stops`` and ``stop_hit_rate`` (the share whose close reached that level
    within the horizon). Without it, or for a bucket where no row had a stop at all, the
    output is exactly what it has always been.
    """
    split = by_source and len({r.get("source") for r in rating_rows}) > 1
    by_rating: dict[str, list[float]] = {}
    stopped: dict[str, list[bool]] = {}
    for row in rating_rows:
        i = _positional_index(close.index, row["date"])
        ticker = row["ticker"]
        if i is None or ticker not in close.columns or i + horizon >= len(close.index):
            continue
        c0, c1 = close[ticker].iloc[i], close[ticker].iloc[i + horizon]
        if pd.isna(c0) or pd.isna(c1):
            continue
        rating = row.get("rating") or "unknown"
        key = f"{rating} ({row.get('source', 'unknown')})" if split else rating
        by_rating.setdefault(key, []).append(float(c1 / c0 - 1.0))
        if stop_rows:
            stop = live_stop(stop_rows, ticker, row["date"]) or row.get("stop_loss")
            if stop is not None:
                path = close[ticker].iloc[i + 1: i + horizon + 1].dropna()
                stopped.setdefault(key, []).append(bool((path <= stop).any()))

    out = {}
    for key, fwds in by_rating.items():
        rule = _HIT_RULES.get(key.split(" (")[0].lower())
        hit_rate = float(sum(1 for f in fwds if rule(f)) / len(fwds)) if rule else None
        out[key] = {"n": len(fwds), "mean_fwd": float(sum(fwds) / len(fwds)), "hit_rate": hit_rate}
        hits = stopped.get(key)
        if hits:
            out[key]["n_stops"] = len(hits)
            out[key]["stop_hit_rate"] = float(sum(hits) / len(hits))
    return out


def to_markdown(summary: dict, ratings: dict) -> str:
    lines = ["# Ledger evaluation"]
    if summary["n_dates"] == 0:
        lines.append("No score dates resolved a forward horizon yet.")
    else:
        lines.append(f"dates={summary['n_dates']}")
        if summary["mean_ic"] is not None:
            lines.append(f"mean rank-IC={summary['mean_ic']:+.3f}")
        if summary["mean_topk_fwd"] is not None:
            lines.append(f"mean top-k fwd={summary['mean_topk_fwd']:+.2%}")
        if summary["mean_excess"] is not None:
            lines.append(
                f"excess vs benchmark={summary['mean_excess']:+.2%}  beat rate={summary['beat_rate']:.0%}"
            )
        if summary["mean_ey_ic"] is not None:
            lines.append(f"mean earnings-yield IC={summary['mean_ey_ic']:+.3f}")
        if summary["mean_rev_ic"] is not None:
            lines.append(f"mean revision-breadth IC={summary['mean_rev_ic']:+.3f}")
        lines.append("")
        lines.append("per-date:")
        for row in summary["per_date"]:
            ic = f"{row['ic']:+.3f}" if row["ic"] is not None else "n/a"
            topk = f"{row['topk_fwd']:+.2%}" if row["topk_fwd"] is not None else "n/a"
            bench = f"{row['bench_fwd']:+.2%}" if row["bench_fwd"] is not None else "n/a"
            lines.append(f"  {row['date']}  n={row['n']}  ic={ic}  topk_fwd={topk}  bench_fwd={bench}")

    if ratings:
        lines.append("")
        lines.append("per-rating:")
        for rating, stats in ratings.items():
            hit = f"{stats['hit_rate']:.0%}" if stats["hit_rate"] is not None else "n/a"
            line = f"  {rating:<12} n={stats['n']}  mean_fwd={stats['mean_fwd']:+.2%}  hit_rate={hit}"
            if "stop_hit_rate" in stats:
                line += f"  stopped={stats['stop_hit_rate']:.0%} of {stats['n_stops']}"
            lines.append(line)

    return "\n".join(lines)
