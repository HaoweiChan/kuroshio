"""TAIEX (台股加權指數) market-regime read for portfolio risk budgeting.

The regime label drives how aggressively the allocator deploys futures margin:
a strong index lets the equity ratio fall toward the aggressive end of the
200–250 band; a weak index pushes it toward the conservative end. Network
failures degrade to a neutral stance so allocation never hard-fails on data.
"""

from __future__ import annotations

from typing import Any, Dict


_STANCE = {
    "bullish": "Lean aggressive — index trend up; deploy toward a ~200% equity ratio.",
    "neutral": "Stay balanced — mixed index trend; hold near a ~225% equity ratio.",
    "bearish": "Be conservative — index below trend; keep a ~250%+ equity ratio buffer.",
}


def _fallback(reason: str) -> Dict[str, Any]:
    return {"regime": "neutral", "stance": _STANCE["neutral"], "detail": reason, "source": "fallback"}


def taiex_regime(*, lookback_days: int = 90) -> Dict[str, Any]:
    """Classify the TAIEX trend as bullish / neutral / bearish."""
    try:
        import yfinance as yf

        hist = yf.Ticker("^TWII").history(period=f"{max(lookback_days, 90)}d")
        closes = hist["Close"].dropna()
        if len(closes) < 60:
            return _fallback("insufficient TAIEX history")
        last = float(closes.iloc[-1])
        ma20 = float(closes.tail(20).mean())
        ma60 = float(closes.tail(60).mean())
        ret_1m = (last / float(closes.iloc[-21]) - 1) * 100 if len(closes) >= 21 else 0.0

        if last > ma20 > ma60:
            regime = "bullish"
        elif last < ma60:
            regime = "bearish"
        else:
            regime = "neutral"

        return {
            "regime": regime,
            "stance": _STANCE[regime],
            "last": round(last, 1),
            "ma20": round(ma20, 1),
            "ma60": round(ma60, 1),
            "ret_1m_pct": round(ret_1m, 2),
            "source": "yfinance ^TWII",
        }
    except Exception as exc:  # noqa: BLE001 - data source is best-effort
        return _fallback(f"TAIEX fetch failed: {exc}")
