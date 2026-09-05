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
ATR_WINDOW = 14  # the ATR the stop ratchet trails by; see engine.propose step 3


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


def trail_inputs(
    panel: Panel, holdings: list[Holding]
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Per-ticker (running high since entry, ATR14, minimum close since entry) for the
    allocator's stop ratchet and its max-adverse-excursion rule (TASK-11).

    "Since entry" is ``entry_date`` inclusive, so a position opened today is measured
    from its own session. A holding without an ``entry_date`` has no such window and is
    absent from all three dicts: the panel's whole lookback is not "since entry", and
    trailing a stop from a high the user never held through is worse than not trailing.

    So is a window the panel does not cover: a holding whose ``entry_date`` predates the
    panel's first row is absent from all three too, because everything read off it would
    be the provider's fetch window under the name "since entry" — the drawdown or high
    before the first row is simply unread. ``cli.py`` fetches back to the oldest
    ``entry_date`` in the book, so this is the provider coming up short, not the default.

    ATR is the mean true range over the last ``ATR_WINDOW`` sessions of the *panel*, not
    of the holding period — it is a volatility estimate, not a since-entry statistic. It
    needs high/low, so it is absent for every ticker on a panel without them, which is
    what stops the ratchet on a hand-built or pre-TASK-11 panel. The running high falls
    back to the closes there, since a close is a session extreme the panel does have.
    """
    close, high, low = panel.close, panel.high, panel.low
    running_high: dict[str, float] = {}
    atr14: dict[str, float] = {}
    min_close: dict[str, float] = {}
    if close.empty:
        return running_high, atr14, min_close

    have_range = high is not None and low is not None
    seen: set[str] = set()
    for holding in holdings:
        ticker, entry_date = holding.ticker, holding.entry_date
        if not entry_date or ticker in seen or ticker not in close.columns:
            continue
        seen.add(ticker)
        if pd.Timestamp(close.index[0]) > pd.Timestamp(entry_date):
            continue
        since = close[ticker].loc[close.index >= entry_date].dropna()
        peaks = since
        if have_range and ticker in high.columns:
            highs = high[ticker].loc[high.index >= entry_date].dropna()
            peaks = highs if not highs.empty else since
        if not since.empty:
            min_close[ticker] = float(since.min())
        if not peaks.empty:
            running_high[ticker] = float(peaks.max())
        if not have_range or ticker not in high.columns or ticker not in low.columns:
            continue
        atr = _atr(high[ticker], low[ticker], close[ticker])
        if atr is not None:
            atr14[ticker] = atr
    return running_high, atr14, min_close


def _atr(high: pd.Series, low: pd.Series, close: pd.Series) -> float | None:
    """Mean true range over the last ``ATR_WINDOW`` sessions, or None when the panel is
    shorter than the window or the last value is a hole. Plain mean (`rolling`), not
    Wilder's smoothing: one window, no seeding, and nothing here needs the exponential
    version's memory of a range that fell out of the window."""
    frame = pd.concat([high, low, close.shift(1)], axis=1).dropna(how="all")
    hi, lo, prev = frame.iloc[:, 0], frame.iloc[:, 1], frame.iloc[:, 2]
    true_range = pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(ATR_WINDOW).mean()
    return None if atr.empty or pd.isna(atr.iloc[-1]) else float(atr.iloc[-1])
