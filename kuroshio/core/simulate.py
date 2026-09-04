"""Walk-forward portfolio simulator — does the allocator's *methodology* make money?

``core/backtest.py`` checks whether ``final_score`` ranks forward returns; it never
calls ``propose()``, so the sizing / swap / trim / max-adverse-excursion rules that
make up the actual methodology have no backtest at all. This module runs them: on
every rebalance date it builds the portfolio from the gated screen, scores the whole
panel (every column but the reference instruments) in one ungated ``score_names``
cross-section so the swap hurdle is a universe percentile, calls ``propose()`` with
``monitor_inputs`` of the panel sliced to that date, applies the returned cards
mechanically, charges ``ips.friction`` per traded leg, and lets weights drift with
prices between rebalances.

Deliberately narrow, same spirit as ``backtest.py``: no verdicts (the swap gate's
verdict floor defaults to "neutral", which every unscored challenger clears), no
themes, and no setup_type / thesis monitoring — a simulated Holding never carries one,
so ``propose``'s thesis rules stay silent and only the MAE forced-decision rule and the
position caps are exercised. ``swaps_this_week=0`` every call, since one ``propose()``
runs per rebalance step: ``ips.turnover.max_swaps_per_week`` therefore caps swaps per
rebalance, not per calendar week. Point-in-time universe membership is the caller's
responsibility, not this module's (see ``backtest.py``'s caveat, printed by the CLI).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from ..types import Candidate, Holding, Panel
from .allocator.engine import propose, swap_hurdle
from .allocator.signals import monitor_inputs


@dataclass
class SimResult:
    dates: list[str]
    nav: list[float]
    ew_nav: list[float]
    bench_nav: list[float] | None
    trades: list[dict] = field(default_factory=list)
    # one entry per rebalance date: {"date": ..., ticker: weight, ...} (holdings only)
    weights: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        years = max(len(self.dates), 1) / 252
        # a SWAP is one sell leg + one buy leg of the same size; every other action
        # (BUY, TRIM, DECIDE, DELIST) is a single leg. Inception buys are excluded:
        # counting them would report 1.0x/yr for a book that never traded again.
        inception = self.dates[0] if self.dates else None
        strat_traded = sum(
            (2 if t["action"] == "SWAP" else 1) * t["weight"]
            for t in self.trades if t["date"] != inception
        )
        out = {
            "n_rebalances": len(self.weights),
            "total_return": self.nav[-1] / self.nav[0] - 1.0,
            "max_drawdown": _max_drawdown(self.nav),
            "ann_turnover": strat_traded / years,
            "n_swaps": sum(1 for t in self.trades if t["action"] == "SWAP"),
            "n_trims": sum(1 for t in self.trades if t["action"] == "TRIM"),
            "n_decides": sum(1 for t in self.trades if t["action"] == "DECIDE"),
            "ew_total_return": self.ew_nav[-1] / self.ew_nav[0] - 1.0,
            "final_holdings": sorted(self.weights[-1].keys() - {"date"}) if self.weights else [],
        }
        if self.bench_nav is not None:
            out["bench_total_return"] = self.bench_nav[-1] / self.bench_nav[0] - 1.0
        return out

    def to_markdown(self) -> str:
        if not self.dates:
            return "# Simulation\n\nNo rebalance dates produced a portfolio."
        s = self.summary()
        lines = [
            f"# Simulation — {s['n_rebalances']} rebalances, {len(self.dates)} sessions",
            f"total return={s['total_return']:+.2%}  max drawdown={s['max_drawdown']:.2%}  "
            f"ann. turnover={s['ann_turnover']:.2f}x",
            f"trades: {s['n_swaps']} swap(s), {s['n_trims']} trim(s), {s['n_decides']} decide(s)",
            f"equal-weight baseline total return={s['ew_total_return']:+.2%}",
        ]
        if "bench_total_return" in s:
            lines.append(f"benchmark total return={s['bench_total_return']:+.2%}")
        lines.append(f"final holdings: {', '.join(s['final_holdings']) or '(none)'}")
        return "\n".join(lines)


def _max_drawdown(nav: list[float]) -> float:
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def _drift(nav: float, cash: float, weights: dict[str, float], close: pd.DataFrame, j: int) -> tuple:
    """One session of price drift: nav *= cash + sum(w * (1+r)), then renormalize.
    A NaN close on either endpoint (a hole, or a name not yet delisted from the sim)
    is treated as a 0% return for that ticker this session."""
    growth = cash
    grown: dict[str, float] = {}
    for t, w in weights.items():
        r = 0.0
        if t in close.columns:
            c0, c1 = close[t].iloc[j - 1], close[t].iloc[j]
            if pd.notna(c0) and pd.notna(c1) and c0 != 0:
                r = c1 / c0 - 1.0
        grown[t] = w * (1.0 + r)
        growth += grown[t]
    nav *= growth
    if growth > 0:
        weights = {t: w / growth for t, w in grown.items()}
        cash /= growth
    return nav, cash, weights


def simulate(
    panel: Panel,
    screen_fn: Callable[..., list[Candidate]],
    score_fn: Callable[..., list[Candidate]],
    ips,
    market: str,
    *,
    step: int = 5,
    top_k: int = 10,
    benchmark: str | None = None,
    min_history: int = 210,
    **screen_kwargs,
) -> SimResult:
    close, volume = panel.close, panel.volume
    if min_history >= len(close.index):
        return SimResult(dates=[], nav=[], ew_nav=[], bench_nav=None)

    roundtrip_pct = swap_hurdle(ips, market)[1]
    reference = {benchmark} | set((screen_kwargs.get("sector_map") or {}).values())
    universe = [c for c in close.columns if c not in reference]
    hard_cap = ips.caps.position_hard_pct / 100
    rebalance_dates = set(range(min_history, len(close.index), step))

    bench_base = None
    if benchmark and benchmark in close.columns:
        b0 = close[benchmark].iloc[min_history]
        bench_base = float(b0) if pd.notna(b0) and b0 != 0 else None

    dates: list[str] = []
    nav_path: list[float] = []
    ew_nav_path: list[float] = []
    bench_path: list[float] | None = [] if bench_base is not None else None
    trades: list[dict] = []
    weights_log: list[dict] = []

    nav = ew_nav = 1.0
    holdings: list[Holding] = []
    cash = ew_cash = 1.0
    ew_weights: dict[str, float] = {}

    for j in range(min_history, len(close.index)):
        asof = str(close.index[j])

        if j > min_history:
            hw = {h.ticker: h.weight for h in holdings}
            nav, cash, hw = _drift(nav, cash, hw, close, j)
            for h in holdings:
                h.weight = hw[h.ticker]
            ew_nav, ew_cash, ew_weights = _drift(ew_nav, ew_cash, ew_weights, close, j)

        if j in rebalance_dates:
            total_cost = 0.0
            eligible = sorted(screen_fn(panel, asof=asof, **screen_kwargs), key=lambda c: c.rank)[:top_k]
            eligible_tickers = [c.ticker for c in eligible]
            score_map: dict[str, float] = {}

            if j == min_history:
                # first rebalance: nothing held yet, nothing to score or propose against,
                # and nothing to charge friction against either — going from all-cash to
                # the starting book is inception, not a policy trade, so NAV starts
                # exactly at 1.0 (the acceptance bar) rather than 1.0 minus a buy-in fee.
                # Its trade rows carry cost 0.0 for the same reason: a record must not claim
                # a fee the NAV path never paid.
                # ponytail: buy weight is capped at the hard cap here too (not just on the
                # next rebalance's TRIM), so a hard cap tighter than 1/top_k never leaves a
                # position over it even for the one rebalance before propose() first runs.
                w = min(1.0 / top_k, hard_cap) if top_k else 0.0
                for t in eligible_tickers:
                    price = close.loc[asof, t] if t in close.columns else float("nan")
                    cash -= w
                    holdings.append(Holding(
                        ticker=t, weight=w,
                        entry_price=float(price) if pd.notna(price) else None, entry_date=asof,
                    ))
                    trades.append({
                        "date": asof, "action": "BUY", "sell": None, "buy": t, "weight": w, "cost": 0.0,
                    })
                # equal-weight baseline is plain 1/top_k — it does not obey the IPS hard
                # cap, since the whole point is to show what an unmanaged equal-weight
                # book would have done against the capped, allocator-managed strategy.
                ew_w = 1.0 / top_k if top_k else 0.0
                ew_weights = {t: ew_w for t in eligible_tickers}
                ew_cash = 1.0 - sum(ew_weights.values())
            else:
                # DELIST — drop any holding with no close today, sold at its last known price.
                delisted = [
                    h for h in holdings
                    if h.ticker not in close.columns or pd.isna(close.loc[asof, h.ticker])
                ]
                for h in delisted:
                    holdings.remove(h)
                    cash += h.weight
                    cost = h.weight * (roundtrip_pct / 100) / 2
                    total_cost += cost
                    trades.append({
                        "date": asof, "action": "DELIST", "sell": h.ticker, "buy": None,
                        "weight": h.weight, "cost": cost,
                    })

                held = {h.ticker for h in holdings}
                # Score the whole cross-section, not held ∪ eligible: pctrank pins its scale
                # to the pool it is handed, so a 20-name pool makes the hurdle a rank
                # distance of three places and the book churns every rebalance
                # (backlog draft-18). Reference instruments are never candidates.
                scored = score_fn(panel, universe, asof=asof, **screen_kwargs)
                score_map = {c.ticker: c.final_score for c in scored}
                for h in holdings:
                    h.score = score_map.get(h.ticker)
                challengers = [c for c in scored if c.ticker in eligible_tickers and c.ticker not in held]

                sub_panel = Panel(close=close.iloc[: j + 1], volume=volume.iloc[: j + 1], institutional=None)
                prices, ma50, session = monitor_inputs(sub_panel)
                cards = propose(
                    holdings, challengers, ips, market,
                    swaps_this_week=0, prices=prices, ma50=ma50, asof=session,
                )

                for card in cards:
                    if card.action == "DECIDE":
                        ticker = card.details.get("ticker")
                        h = next((x for x in holdings if x.ticker == ticker), None)
                        if h is None:
                            continue
                        holdings.remove(h)
                        cash += h.weight
                        cost = h.weight * (roundtrip_pct / 100) / 2
                        total_cost += cost
                        trades.append({
                            "date": asof, "action": "DECIDE", "sell": ticker, "buy": None,
                            "weight": h.weight, "cost": cost,
                        })
                    elif card.action == "TRIM":
                        h = next((x for x in holdings if x.ticker == card.sell), None)
                        if h is None or h.weight <= hard_cap:
                            continue
                        trimmed = h.weight - hard_cap
                        h.weight = hard_cap
                        cash += trimmed
                        cost = trimmed * (roundtrip_pct / 100) / 2
                        total_cost += cost
                        trades.append({
                            "date": asof, "action": "TRIM", "sell": card.sell, "buy": None,
                            "weight": trimmed, "cost": cost,
                        })
                    elif card.action == "SWAP":
                        h = next((x for x in holdings if x.ticker == card.sell), None)
                        if h is None:
                            continue  # already killed by a DECIDE this round
                        holdings.remove(h)
                        price = close.loc[asof, card.buy] if card.buy in close.columns else float("nan")
                        holdings.append(Holding(
                            ticker=card.buy, weight=h.weight, score=score_map.get(card.buy),
                            entry_price=float(price) if pd.notna(price) else None, entry_date=asof,
                        ))
                        cost = h.weight * (roundtrip_pct / 100)  # both legs = the full round-trip
                        total_cost += cost
                        trades.append({
                            "date": asof, "action": "SWAP", "sell": card.sell, "buy": card.buy,
                            "weight": h.weight, "cost": cost,
                        })
                    # ALERT: ignored — nothing to apply mechanically.

                # ponytail: cash redeploy — buy the top-ranked eligible name not held, one
                # at a time, until cash runs out or nothing eligible is left to buy. A real
                # cash rule (position sizing by conviction, partial fills, etc.) is backlog
                # task-1; this is the sim's stand-in. Also capped at the hard cap, for the
                # same reason as the first-rebalance buy above.
                per_name = min(1.0 / top_k, hard_cap) if top_k else 0.0
                held = {h.ticker for h in holdings}
                for t in eligible_tickers:
                    if cash <= 1e-9:
                        break
                    if t in held:
                        continue
                    w = min(cash, per_name)
                    cash -= w
                    price = close.loc[asof, t] if t in close.columns else float("nan")
                    cost = w * (roundtrip_pct / 100) / 2
                    total_cost += cost
                    holdings.append(Holding(
                        ticker=t, weight=w, score=score_map.get(t),
                        entry_price=float(price) if pd.notna(price) else None, entry_date=asof,
                    ))
                    trades.append({
                        "date": asof, "action": "BUY", "sell": None, "buy": t, "weight": w, "cost": cost,
                    })
                    held.add(t)

                # equal-weight baseline: retarget to this round's eligible set.
                new_ew = {t: 1.0 / top_k for t in eligible_tickers} if top_k else {}
                ew_cost = sum(
                    abs(new_ew.get(t, 0.0) - ew_weights.get(t, 0.0)) * (roundtrip_pct / 100) / 2
                    for t in set(ew_weights) | set(new_ew)
                )
                ew_weights = new_ew
                ew_cash = 1.0 - sum(new_ew.values())
                ew_nav *= (1.0 - ew_cost)

            nav *= (1.0 - total_cost)
            weights_log.append({"date": asof, **{h.ticker: h.weight for h in holdings}})

        dates.append(asof)
        nav_path.append(nav)
        ew_nav_path.append(ew_nav)
        if bench_path is not None:
            bench_path.append(float(close[benchmark].iloc[j]) / bench_base)

    return SimResult(
        dates=dates, nav=nav_path, ew_nav=ew_nav_path, bench_nav=bench_path,
        trades=trades, weights=weights_log,
    )
