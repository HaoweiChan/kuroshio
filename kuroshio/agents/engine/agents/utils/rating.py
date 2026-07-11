"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)

# zh-TW rating vocabulary (Kuroshio Phase 1 F2). When output_lang=zh-TW and a
# provider's structured-output path fails, the free-text fallback localizes
# the whole decision — including the rating line ("**評等：加碼/看多**") — so the
# English passes above find nothing and every verdict silently flattened to
# the "Hold" default (observed live: MU 2026-07-11). Terms mirror
# config/i18n/zh-TW.yaml. Only the 評等/評級-labelled line is scanned, ordered
# most-specific-first, because words like 加碼/持有 appear casually in prose.
_ZH_RATING_LABEL_RE = re.compile(r"評[等級]")
_ZH_RATING_TERMS: tuple[tuple[str, str], ...] = (
    ("加碼", "Overweight"),
    ("看多", "Overweight"),
    ("減碼", "Underweight"),
    ("看空", "Underweight"),
    ("買進", "Buy"),
    ("買入", "Buy"),
    ("賣出", "Sell"),
    ("持有", "Hold"),
)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from prose text.

    Three-pass strategy:
    1. Look for an explicit "Rating: X" label (tolerant of markdown bold).
    2. Look for a zh-TW "評等：X" label line (localized free-text fallback).
    3. Fall back to the first 5-tier rating word found anywhere in the text.

    Returns a Title-cased rating string, or ``default`` if no rating word appears.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    for line in text.splitlines():
        if _ZH_RATING_LABEL_RE.search(line):
            for term, rating in _ZH_RATING_TERMS:
                if term in line:
                    return rating

    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize()

    return default
