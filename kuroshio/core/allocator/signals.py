"""core/allocator — the panel-derived inputs `propose`'s thesis monitoring needs.

`engine.propose` is a pure function over plain dataclasses: no panel, no provider
(ARCHITECTURE.md design rules 3 and 5). The monitoring rules it dispatches on
setup_type still need two numbers per ticker, so they are computed here, from a
Panel, and handed in as plain dicts by whoever holds the panel (cli.cmd_propose).

MA50 is this repo's first trend window outside a screener profile — `screening/us.py`
MA_S/MA_M/MA_L and `screening/tw.py` MA20/MA60 are those profiles' own Stage-1 gates
and change with them; this one belongs to a monitoring rule and is deliberately not
shared with either.
"""

from __future__ import annotations

import pandas as pd

from kuroshio.types import Holding, Panel

MA_TREND = 50  # the trend_add break window; see engine.propose step 3
BOOK_VOL_WINDOW = 20  # trailing-session window book_vol() and engine.propose step 2b share


def monitor_inputs(panel: Panel) -> tuple[dict[str, float], dict[str, float], str]:
    """Return (last close, MA50, session label) as of the panel's final session.

    MA50 is the mean of each ticker's last MA_TREND *sessions that traded*, not of the
    last MA_TREND rows: a panel column carries NaN holes wherever that ticker did not
    trade on a day some other ticker did (FinMind returns per-ticker suspension days;
    `providers/yf.py:_shape_panel` keeps rows on the reference ticker's calendar), and
    `rolling().mean()` — pandas defaults `min_periods` to the window — would void the
    average of a ticker with 199 good sessions over one hole.

    A ticker with fewer than MA_TREND traded sessions, or no close on the final one, is
    simply absent from the dict; `propose` names such positions as unmonitored rather
    than treating a missing number as "nothing is wrong".
    """
    close = panel.close
    if close.empty:
        return {}, {}, ""
    last = {t: float(v) for t, v in close.iloc[-1].items() if pd.notna(v)}
    # ponytail: holes are skipped, not counted, so a long suspension averages across a
    # stale window. The panel's own lookback bounds how stale; a per-ticker staleness
    # check belongs with the ATR/high-low work (tasks/TODO.md T38).
    ma = {}
    for ticker, series in close.items():
        traded = series.dropna()
        if len(traded) >= MA_TREND:
            ma[ticker] = float(traded.iloc[-MA_TREND:].mean())
    return last, ma, str(close.index[-1])


def book_vol(panel: Panel, holdings: list[Holding], window: int = BOOK_VOL_WINDOW) -> float | None:
    """Annualized realized vol of the book's daily return over the trailing `window`
    sessions, as a percent (24.1, not 0.241) — the unit `caps.book_vol_target_pct` and
    the SCALE card are written in. Mirrors `scripts/funnel_lab.py:Lab.walk`'s vol-target
    arithmetic (trailing-20-session weighted return, `std() * sqrt(252)`), except weights
    here are renormalized over the holdings that actually have a close somewhere in the
    window: a ticker missing from the panel would otherwise be silently zeroed into the
    book return every session, understating the real vol rather than just excluding a name
    this run can't see. A hole on one session for a ticker that does trade elsewhere in
    the window is a 0% return for that name that day, same as `simulate._drift`.

    None when there's nothing to compute: fewer than `window + 1` sessions of history
    (need `window` daily returns), or no holding with a usable close in the window.
    """
    close = panel.close
    if not holdings or len(close.index) < window + 1:
        return None
    recent = close.iloc[-(window + 1):]
    rets = recent.pct_change().iloc[1:]

    usable = [h for h in holdings if h.ticker in close.columns and recent[h.ticker].notna().any()]
    total_weight = sum(h.weight for h in usable)
    if not usable or total_weight <= 0:
        return None
    book = sum(rets[h.ticker].fillna(0.0) * (h.weight / total_weight) for h in usable)
    return float(book.std() * (252**0.5)) * 100
