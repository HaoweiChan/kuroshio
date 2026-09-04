#!/usr/bin/env python3
"""Funnel lab — which price-only ranking, held equal-weight top-k on a point-in-time
S&P 500, beats SPY *through 2025-12-31* (before the 2026 blowoff)?

Usage: python scripts/funnel_lab.py MEMBERS.csv [--panel cache.pkl] [--end YYYY-MM-DD] [--years N]
       [--cutoff YYYY-MM-DD]

``--end``/``--years`` move the window (the out-of-sample run ends 2021-07-31); ``--cutoff``
is the date the "through" column reports at (default 2025-12-31, the pre-blowoff bar).

MEMBERS.csv comes from scripts/sp500_members.py. The panel is fetched through the
yfinance provider (benchmark first — see cli.py's reference-row note) and cached to
``--panel`` when given, so a rerun is seconds. No propose(): every line is "EW top-k
of one ranker, rebalanced every `step` sessions, friction per leg, cash for unfilled
slots". The grid is pre-declared in RANKERS × STEPS × TOPS; the robustness block only
varies the winner. Results and caveats: docs/backtest-2026-09.md.
"""

from __future__ import annotations

import argparse
import bisect
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kuroshio.core.screening.us import DOLLAR_VOL_MIN, PRICE_MIN  # noqa: E402

BENCH = "SPY"
FRICTION_RT = 0.02 / 100  # ips-balanced us_roundtrip_pct
MIN_HISTORY = 260  # 252 sessions of 12-1 momentum + a month
STEPS, TOPS = (5, 21), (10, 20)


class Lab:
    def __init__(self, panel, members: pd.DataFrame):
        self.close, self.volume = panel.close, panel.volume
        self.idx = list(self.close.index)
        self.mdates = list(members.date)
        self.msets = [frozenset(t.split()) for t in members.tickers]
        c = self.close
        self.ma20, self.ma50, self.ma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
        self.hi60 = c.rolling(60).max()
        self.ret5, self.ret20, self.ret60 = c / c.shift(5) - 1, c / c.shift(20) - 1, c / c.shift(60) - 1
        self.ret126 = c / c.shift(126) - 1
        self.mom_12_1 = c.shift(21) / c.shift(252) - 1
        self.avg_vol20 = self.volume.rolling(20).mean()
        self.dollar_vol = c * self.avg_vol20

    def live(self, i: int) -> pd.Index:
        """Members on session i with a close and the US profile's liquidity floor."""
        row = self.close.iloc[i]
        ok = row.notna() & (row >= PRICE_MIN) & (self.dollar_vol.iloc[i] >= DOLLAR_VOL_MIN)
        mem = self.msets[max(bisect.bisect_right(self.mdates, self.idx[i]) - 1, 0)]
        return pd.Index([t for t in row.index[ok] if t in mem])

    # --- rankers: fn(i) -> tickers, best first ---------------------------------------
    def r_gate_momentum(self, i):
        """The current US profile's gates and composite, reimplemented on the lab's indicators."""
        t = self.live(i)
        c, s, m, lo = self.close.iloc[i][t], self.ma20.iloc[i][t], self.ma50.iloc[i][t], self.ma200.iloc[i][t]
        ok = (c > s) & (s > m) & (m > lo) & (c >= 0.9 * self.hi60.iloc[i][t]) & (self.ret5.iloc[i][t] < 0.25)
        t = t[ok.fillna(False).values]
        c = self.close.iloc[i][t]
        mom = (c / self.ma50.iloc[i][t] - 1) + (c / self.ma200.iloc[i][t] - 1)
        r20, r60 = self.ret20.iloc[i], self.ret60.iloc[i]
        rs = (r20[t] - r20[BENCH]) + (r60[t] - r60[BENCH])
        vol = self.volume.iloc[i][t] / self.avg_vol20.iloc[i][t]
        score = 0.333 * mom.rank(pct=True) + 0.267 * rs.rank(pct=True) + 0.2 * vol.rank(pct=True)
        return list(score.sort_values(ascending=False).index)

    def r_mom_12_1(self, i):
        return list(self.mom_12_1.iloc[i][self.live(i)].dropna().sort_values(ascending=False).index)

    def r_mom_12_1_trend(self, i):
        t = self.live(i)
        ok = (self.close.iloc[i][t] > self.ma200.iloc[i][t]).fillna(False).values
        return list(self.mom_12_1.iloc[i][t[ok]].dropna().sort_values(ascending=False).index)

    def _dip_pool(self, i):
        t = self.live(i)
        c, m, lo = self.close.iloc[i][t], self.ma50.iloc[i][t], self.ma200.iloc[i][t]
        dd = c / self.hi60.iloc[i][t] - 1
        return t[((c > lo) & (c < m) & (dd <= -0.08) & (dd >= -0.25)).fillna(False).values]

    def r_dip_leader_mom(self, i):
        """Pullback inside an intact uptrend, ranked by 12-1 momentum (the 'leader' test)."""
        return list(self.mom_12_1.iloc[i][self._dip_pool(i)].dropna().sort_values(ascending=False).index)

    def r_dip_leader_rs6(self, i):
        pool = self._dip_pool(i)
        rs = self.ret126.iloc[i][pool] - self.ret126.iloc[i][BENCH]
        return list(rs.dropna().sort_values(ascending=False).index)

    def breadth_on(self, i) -> bool:
        t = self.live(i)
        return bool((self.close.iloc[i][t] > self.ma200.iloc[i][t]).mean() >= 0.5)

    # --- EW top-k walk -------------------------------------------------------------------
    def ew_walk(self, ranker, step, top_k, regime=None, friction_rt=FRICTION_RT):
        close = self.close
        nav, cash, w, traded = 1.0, 1.0, {}, 0.0
        navs = []
        for i in range(MIN_HISTORY, len(self.idx)):
            if i > MIN_HISTORY:
                grown = {}
                for t, wt in w.items():
                    c0, c1 = close[t].iloc[i - 1], close[t].iloc[i]
                    r = 0.0 if pd.isna(c0) or pd.isna(c1) else c1 / c0 - 1
                    grown[t] = wt * (1 + r)
                g = cash + sum(grown.values())
                nav *= g
                w, cash = {t: v / g for t, v in grown.items()}, cash / g
            if (i - MIN_HISTORY) % step == 0:
                picks = ranker(i)[:top_k] if (regime is None or regime(i)) else []
                new = {t: 1 / top_k for t in picks}
                cost = sum(abs(new.get(t, 0) - w.get(t, 0)) for t in set(w) | set(new))
                traded += cost
                nav *= 1 - cost * friction_rt / 2
                w, cash = new, 1 - sum(new.values())
            navs.append(nav)
        return pd.Series(navs, index=pd.to_datetime(self.idx[MIN_HISTORY:])), traded

    def spy(self) -> pd.Series:
        s = self.close[BENCH].iloc[MIN_HISTORY:]
        return pd.Series(s.values / s.values[0], index=pd.to_datetime(s.index))

    def ic(self, score_at, horizon=20, step=21) -> tuple[float, float, int]:
        """Mean Spearman rank-IC of score vs forward return, share of positive months, n."""
        ics = []
        for i in range(MIN_HISTORY, len(self.idx) - horizon, step):
            t = self.live(i)
            fwd = self.close.iloc[i + horizon][t] / self.close.iloc[i][t] - 1
            d = pd.DataFrame({"m": score_at(i, t), "f": fwd}).dropna()
            if len(d) > 20:
                ics.append(d["m"].rank().corr(d["f"].rank()))
        a = np.array(ics)
        return float(a.mean()), float((a > 0).mean()), len(a)


CUTOFF = "2025-12-31"


def report(name: str, nav: pd.Series, traded: float, spy: pd.Series) -> None:
    ye = nav.resample("YE").last()
    y = ye.pct_change()
    y.iloc[0] = ye.iloc[0] - 1
    thru25, spy25 = nav.loc[:CUTOFF].iloc[-1] - 1, spy.loc[:CUTOFF].iloc[-1] - 1
    yearly = "  ".join(f"{k.year}:{v:+.0%}" for k, v in y.items())
    mdd = (nav / nav.cummax() - 1).min()
    print(
        f"{name:<40} total {nav.iloc[-1] - 1:+7.1%}  thru {CUTOFF[:4]} {thru25:+7.1%}"
        f" ({thru25 - spy25:+.1%} vs SPY)  mdd {mdd:6.1%}"
        f"  turnover {traded / (len(nav) / 252):4.1f}x  | {yearly}"
    )


def main(argv: list[str] | None = None) -> int:
    global CUTOFF
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("members")
    ap.add_argument("--panel", help="pickle cache for the fetched Panel (created if missing)")
    ap.add_argument("--end", help="last session to fetch (default: today)")
    ap.add_argument("--years", type=float, default=5.0, help="simulation years before --end")
    ap.add_argument("--cutoff", default=CUTOFF, help="date the 'through' column reports at")
    args = ap.parse_args(argv)
    CUTOFF = args.cutoff

    members = pd.read_csv(args.members)
    if args.panel and Path(args.panel).exists():
        panel = pickle.load(open(args.panel, "rb"))
    else:
        from kuroshio.providers.yf import YFinanceProvider

        union = sorted(set().union(*(set(t.split()) for t in members.tickers)))
        panel = YFinanceProvider().fetch_panel([BENCH] + union, int(args.years * 365) + 420, end=args.end)
        if args.panel:
            pickle.dump(panel, open(args.panel, "wb"))
    lab = Lab(panel, members)
    spy = lab.spy()
    spy25 = spy.loc[:CUTOFF].iloc[-1] - 1
    print(f"window {lab.idx[MIN_HISTORY]} -> {lab.idx[-1]}")
    print(f"SPY total {spy.iloc[-1] - 1:+.1%}, thru {CUTOFF} {spy25:+.1%}\n")

    nav, tr = lab.ew_walk(lambda i: [BENCH], 5, 1, regime=lab.breadth_on)
    report("SPY when breadth(>MA200) >= 50%, else cash", nav, tr, spy)
    print()
    rankers = {
        "gate_momentum(current)": lab.r_gate_momentum,
        "mom_12_1": lab.r_mom_12_1,
        "mom_12_1_trend": lab.r_mom_12_1_trend,
        "dip_leader_mom": lab.r_dip_leader_mom,
        "dip_leader_rs6": lab.r_dip_leader_rs6,
    }
    for name, fn in rankers.items():
        for step in STEPS:
            for top_k in TOPS:
                nav, tr = lab.ew_walk(fn, step, top_k)
                report(f"{name} step{step} top{top_k}", nav, tr, spy)
        print()
    for name in ("mom_12_1", "dip_leader_mom"):
        nav, tr = lab.ew_walk(rankers[name], 21, 20, regime=lab.breadth_on)
        report(f"{name} step21 top20 +breadth", nav, tr, spy)

    print("\n--- robustness of the winner (12-1 momentum) ---")
    for lb, skip in ((252, 0), (126, 21), (189, 21), (252, 42)):
        mom = lab.close.shift(skip) / lab.close.shift(lb) - 1
        def ranker(i, mom=mom):
            return list(mom.iloc[i][lab.live(i)].dropna().sort_values(ascending=False).index)

        nav, tr = lab.ew_walk(ranker, 21, 20)
        report(f"mom_{lb}_{skip} step21 top20", nav, tr, spy)
    for step, k in ((21, 30), (21, 50), (42, 20)):
        nav, tr = lab.ew_walk(lab.r_mom_12_1, step, k)
        report(f"mom_12_1 step{step} top{k}", nav, tr, spy)
    for rt in (0.001, 0.003):
        nav, tr = lab.ew_walk(lab.r_mom_12_1, 21, 20, friction_rt=rt)
        report(f"mom_12_1 step21 top20 friction {rt:.2%}", nav, tr, spy)

    print("\n--- rank-IC vs 20d forward return, monthly ---")
    m, share, n = lab.ic(lambda i, t: lab.mom_12_1.iloc[i][t])
    print(f"12-1 momentum, liquid members:   mean IC {m:+.3f}  positive months {share:.0%}  n={n}")

    def gate_score(i, t):
        order = lab.r_gate_momentum(i)
        return pd.Series({tk: -r for r, tk in enumerate(order)}).reindex(t)

    m, share, n = lab.ic(gate_score)
    print(f"current gate composite, gated pool: mean IC {m:+.3f}  positive months {share:.0%}  n={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
