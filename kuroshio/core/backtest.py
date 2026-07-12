"""Minimal walk-forward backtest harness — does ``final_score`` predict forward returns?

Ported stats-only from a production US screener's ``cmd_backtest`` (top-k forward
returns, excess vs benchmark, beat rate, rank-IC, score-quintile table). Everything
else (data-fetching, point-in-time universe membership, congress/13F overlays) is
deliberately out of scope — see ARCHITECTURE.md.

CAVEAT: the panel's columns *are* the universe. ``screen_fn`` only looks backward
from ``asof``, so re-using one full panel across rebalance dates is price-wise
point-in-time-safe — but if the caller supplies only today's survivors (e.g. the
current S&P 500 roster fetched N years back), results carry survivorship bias.
Point-in-time universe membership is the caller's responsibility, not this module's.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from ..types import Candidate, Panel


@dataclass
class BacktestResult:
    records: list[dict]                       # one per rebalance date
    horizon: int
    top_k: int
    pooled: list[tuple[float, float]] = field(default_factory=list)  # (score, fwd) across all dates

    def summary(self) -> dict:
        if not self.records:
            return {"n_rebalances": 0}
        df = pd.DataFrame(self.records)
        out: dict = {
            "n_rebalances": len(df),
            "mean_topk_fwd": float(df["topk_fwd"].mean()),
        }
        bench = df["bench_fwd"].dropna()
        if not bench.empty:
            excess = df["topk_fwd"] - df["bench_fwd"]
            out["mean_excess_vs_bench"] = float(excess.mean())
            out["beat_rate"] = float((excess > 0).mean())
        ic = df["ic"].dropna()
        if not ic.empty:
            out["mean_ic"] = float(ic.mean())
        out["quintiles"] = self._quintiles()
        return out

    def _quintiles(self) -> dict[str, dict]:
        if len(self.pooled) < 10:
            return {}
        pool = pd.DataFrame(self.pooled, columns=["score", "fwd"])
        # labels=False (bin index, not fixed label list) survives duplicates="drop"
        # collapsing to fewer than 5 bins on low-variance score data.
        pool["q"] = pd.qcut(pool["score"], 5, labels=False, duplicates="drop")
        by_q = pool.groupby("q")["fwd"].agg(["mean", "count"])
        return {
            f"Q{int(q) + 1}": {"mean": float(r["mean"]), "n": int(r["count"])} for q, r in by_q.iterrows()
        }

    def to_markdown(self) -> str:
        s = self.summary()
        lines = [f"# Backtest — {self.horizon}d forward returns, top-{self.top_k}"]
        if s["n_rebalances"] == 0:
            lines.append("No rebalance dates produced candidates.")
            return "\n".join(lines)
        lines.append(
            f"rebalances={s['n_rebalances']}  mean top-{self.top_k} fwd={s['mean_topk_fwd']:+.2%}"
        )
        if "mean_excess_vs_bench" in s:
            lines.append(
                f"excess vs benchmark={s['mean_excess_vs_bench']:+.2%}  beat rate={s['beat_rate']:.0%}"
            )
        if "mean_ic" in s:
            lines.append(f"mean rank-IC={s['mean_ic']:+.3f}")
        if s["quintiles"]:
            lines.append("")
            lines.append("score-quintile mean forward return (pooled):")
            for q, row in s["quintiles"].items():
                lines.append(f"  {q:<3} {row['mean']:+.2%}  (n={row['n']})")
        return "\n".join(lines)


def walkforward(
    panel: Panel,
    screen_fn: Callable[..., list[Candidate]],
    *,
    horizon: int = 20,
    step: int = 5,
    top_k: int = 10,
    benchmark: str | None = None,
    min_history: int = 210,
    **screen_kwargs,
) -> BacktestResult:
    """Rebalance every ``step`` sessions from ``min_history`` up to ``len(panel) - horizon``,
    scoring each date's candidates against their actual ``horizon``-day forward return."""
    close = panel.close
    records: list[dict] = []
    pooled: list[tuple[float, float]] = []

    for i in range(min_history, len(close.index) - horizon, step):
        asof = str(close.index[i])
        candidates = sorted(screen_fn(panel, asof=asof, **screen_kwargs), key=lambda c: c.rank)
        if not candidates:
            continue

        scored: list[tuple[Candidate, float]] = []
        for c in candidates:
            if c.ticker not in close.columns:
                continue
            c0, c1 = close[c.ticker].iloc[i], close[c.ticker].iloc[i + horizon]
            if pd.isna(c0) or pd.isna(c1):
                continue
            scored.append((c, float(c1 / c0 - 1.0)))
        if not scored:
            continue

        topk = scored[:top_k]
        topk_fwd = float(sum(fwd for _, fwd in topk) / len(topk))

        bench_fwd = None
        if benchmark and benchmark in close.columns:
            b0, b1 = close[benchmark].iloc[i], close[benchmark].iloc[i + horizon]
            if pd.notna(b0) and pd.notna(b1):
                bench_fwd = float(b1 / b0 - 1.0)

        ic = None
        if len(scored) > 2:
            pair = pd.DataFrame(
                {"score": [c.final_score for c, _ in scored], "fwd": [fwd for _, fwd in scored]}
            )
            ic = float(pair["score"].rank().corr(pair["fwd"].rank()))

        records.append({
            "date": asof,
            "n_candidates": len(candidates),
            "topk_fwd": topk_fwd,
            "bench_fwd": bench_fwd,
            "ic": ic,
        })
        pooled.extend((c.final_score, fwd) for c, fwd in scored)

    return BacktestResult(records=records, horizon=horizon, top_k=top_k, pooled=pooled)
