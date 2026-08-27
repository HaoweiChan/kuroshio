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


def monitor_inputs(panel: Panel) -> tuple[dict[str, float], dict[str, float]]:
    """Return (last close, MA50) per ticker, as of the panel's final session.

    A ticker whose value is NaN — no data at all, or fewer than MA_TREND sessions of
    it — is simply absent from the dict; `propose` names such positions as unmonitored
    rather than treating a missing number as "nothing is wrong".
    """
    close = panel.close
    if close.empty:
        return {}, {}
    last = close.iloc[-1]
    ma = close.rolling(MA_TREND).mean().iloc[-1]
    drop_na = lambda row: {t: float(v) for t, v in row.items() if pd.notna(v)}  # noqa: E731
    return drop_na(last), drop_na(ma)
