"""TinBoker podcast-mention fetcher for Taiwan ticker sentiment.

TinBoker (tinboker.com) transcribes the major Taiwanese finance podcasts and
extracts, per episode and ticker, a one-line thesis, a five-tier sentiment
label, reasons/risks, and — once enough trading days have passed — the
forward return after the mention. That is a source no US-style feed has:
who said what about ``2330`` this month, and whether that show has been
right before. Two public, keyless endpoints, stdlib ``urllib`` only, same
convention as ``ptt.py``:

  ``/api/ticker-insights/by-ticker/{code}``  — theses in a date window
  ``/api/tickers/{code}/mentions``           — every mention on record,
                                               with r1d/r5d/r20d/r60d (in %)

Failure semantics mirror ``ptt.py``: a fetch failure is ``None`` internally
(never ``[]``), and surfaces as a marker so the analyst never reads a network
blip as "no podcast is discussing this ticker" — which, for a TW name, is
itself a signal worth reporting when it is real.
"""

from __future__ import annotations

import http.client
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .ptt import _bare_code

logger = logging.getLogger(__name__)

_BASE = "https://api.tinboker.com"
_UA = "kuroshio/0.x (+https://github.com/HaoweiChan/kuroshio)"
_MENTIONS_LIMIT = 200  # API max; the track record wants every mention on file
_MAX_THESES = 12  # a large cap draws 70+ theses a month; the tally carries the rest
_BULL = ("BULLISH", "STRONG_BULLISH")
_BEAR = ("BEARISH", "STRONG_BEARISH")


def _get_json(url: str, timeout: float) -> list | dict | None:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        logger.warning("TinBoker fetch failed for %s: %s", url, exc)
        return None


def _fetch_insights(code: str, start_date: str, end_date: str, timeout: float) -> list[dict] | None:
    qs = urlencode({"start_date": start_date, "end_date": end_date})
    data = _get_json(f"{_BASE}/api/ticker-insights/by-ticker/{code}?{qs}", timeout)
    return data if isinstance(data, list) else None


def _fetch_mentions(code: str, timeout: float) -> list[dict] | None:
    data = _get_json(f"{_BASE}/api/tickers/{code}/mentions?limit={_MENTIONS_LIMIT}", timeout)
    if not isinstance(data, dict) or not isinstance(data.get("mentions"), list):
        return None
    return data["mentions"]


def _hit(label: str, r: float) -> bool | None:
    """Did the call's direction match the forward return? ``None`` = neutral, not scored."""
    if label in _BULL:
        return r > 0
    if label in _BEAR:
        return r < 0
    return None


def _track_record(mentions: list[dict], horizon: str = "r20d") -> list[str]:
    """Per-show lines: mentions on record, how many have a resolved forward
    return, directional hit rate among those, mean forward return."""
    per: dict[str, dict] = defaultdict(lambda: {"n": 0, "resolved": 0, "hits": 0, "scored": 0, "sum": 0.0})
    for m in mentions:
        show = m.get("podcaster") or "?"
        row = per[show]
        row["n"] += 1
        r = (m.get("performance") or {}).get(horizon)
        if r is None:
            continue
        row["resolved"] += 1
        row["sum"] += float(r)
        hit = _hit(str(m.get("sentiment_label") or "").upper(), float(r))
        if hit is not None:
            row["scored"] += 1
            row["hits"] += int(hit)

    lines = []
    for show, row in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        if row["resolved"]:
            mean = row["sum"] / row["resolved"]  # API returns percent already
            lines.append(
                f"  {show}: {row['n']} mentions, {row['resolved']} with {horizon},"
                f" directional hit {row['hits']}/{row['scored']}, mean {horizon} {mean:+.1f}%"
            )
        else:
            lines.append(f"  {show}: {row['n']} mentions, none old enough for a {horizon} yet")
    return lines


def _insight_lines(insights: list[dict]) -> list[str]:
    lines = []
    for i in insights:
        date = str(i.get("podcast_launch_time") or "")[:10] or "?"
        head = f"  [{date} · {i.get('podcaster') or '?'} · {i.get('sentiment_label') or '?'} · {i.get('time_horizon') or '?'}]"
        lines.append(f"{head} {i.get('bluf_thesis') or ''}".rstrip())
        reasons = "; ".join(r.get("title", "") for r in i.get("reasons") or [] if r.get("title"))
        if reasons:
            lines.append(f"    reasons: {reasons}")
        risks = "; ".join(
            f"{r.get('title', '')} ({r['severity']})" if r.get("severity") else r.get("title", "")
            for r in i.get("risks") or []
            if r.get("title")
        )
        if risks:
            lines.append(f"    risks: {risks}")
    return lines


def fetch_tinboker_mentions(
    ticker: str,
    end_date: str,
    lookback_days: int = 30,
    timeout: float = 10.0,
) -> str:
    """Podcast theses on ``ticker`` from the last ``lookback_days`` plus each
    show's forward-return track record on that ticker, as a plaintext block
    ready for prompt injection. Never raises.

    The window is wider than the 7-day social window on purpose: the shows
    publish weekly, so a 7-day slice is often one episode or none.
    """
    code = _bare_code(ticker)
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start_date = (end - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    insights = _fetch_insights(code, start_date, end_date, timeout)
    mentions = _fetch_mentions(code, timeout)

    if insights is None and mentions is None:
        return (
            f"<TINBOKER DATA UNAVAILABLE — api.tinboker.com failed this run for {code}."
            " This is a data-pipeline failure: do NOT interpret it as 'no podcast covers"
            " this name'. Base the read on the other sources.>"
        )

    notes = []
    if insights is None:
        notes.append(
            f"<FETCH FAILED for TinBoker insights window {start_date}→{end_date} — treat as"
            " MISSING DATA, not as absence of coverage>"
        )
    if mentions is None:
        notes.append("<FETCH FAILED for TinBoker mention track record — treat as MISSING DATA>")

    parts = []
    if insights is not None:
        shows = {i.get("podcaster") for i in insights if i.get("podcaster")}
        if insights:
            labels = [str(i.get("sentiment_label") or "").upper() for i in insights]
            bull, bear = sum(l in _BULL for l in labels), sum(l in _BEAR for l in labels)
            header = (
                f"TinBoker 播客提及 — {len(insights)} theses on {code} from {len(shows)} shows,"
                f" {start_date}→{end_date}: {bull} bullish / {len(labels) - bull - bear} neutral"
                f" / {bear} bearish; newest {min(_MAX_THESES, len(insights))} shown:"
            )
            parts.append("\n".join([header] + _insight_lines(insights[:_MAX_THESES])))
        else:
            parts.append(
                f"<no podcast in TinBoker's tracked set discussed {code} between {start_date}"
                f" and {end_date} — real silence, not a fetch failure>"
            )
    if mentions:
        header = (
            f"Track record — every {code} mention on file ({len(mentions)}), forward return"
            " measured from the mention-day close; 'hit' = call direction matched the sign:"
        )
        parts.append("\n".join([header] + _track_record(mentions)))

    return "\n\n".join(notes + parts)
