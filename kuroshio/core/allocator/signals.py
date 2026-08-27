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

from kuroshio.types import Panel

MA_TREND = 50  # the trend_add break window; see engine.propose step 3


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
