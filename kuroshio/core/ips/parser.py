"""IPS markdown parsing: YAML frontmatter + free-text philosophy body."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .schema import IPS, VERDICT_ORDER, CapExemption, Caps, Friction, Notify, Turnover, Universe

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*\n?", re.DOTALL)

_KNOWN_TOP_KEYS = {
    "version", "risk_profile", "style", "lang", "universe", "caps",
    "turnover", "friction", "notify",
}
# what a `caps.exemptions` entry may relax — see Caps.max_adverse_excursion_pct
# for why the MAE threshold is not one of them.
_CAP_FIELDS = {"position_pct", "position_hard_pct", "theme_pct"}
_KNOWN_RISK_PROFILES = {"conservative", "balanced", "aggressive"}


def parse_ips(source: str | Path) -> IPS:
    """Parse an IPS from a file path or raw markdown text.

    `source` is treated as a path when it has no newline and exists as a file;
    otherwise it's treated as raw markdown text.
    """
    text = _read(source)
    return _parse_text(text)


def _read(source: str | Path) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    candidate = Path(source)
    if "\n" in source or not candidate.exists():
        return source
    return candidate.read_text(encoding="utf-8")


def _parse_text(text: str) -> IPS:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return IPS(philosophy=text.strip())

    raw = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw, dict):  # user file with scalar/list frontmatter — degrade, don't crash
        raw = {}
    philosophy = text[match.end():].strip()

    universe_raw = raw.get("universe") or {}
    caps_raw = raw.get("caps") or {}
    turnover_raw = raw.get("turnover") or {}
    friction_raw = raw.get("friction") or {}
    notify_raw = raw.get("notify") or {}

    exemptions = [
        CapExemption(ticker=e.get("ticker", ""), cap=e.get("cap", ""), reason=e.get("reason", ""))
        for e in caps_raw.get("exemptions") or []
        if isinstance(e, dict)
    ]

    return IPS(
        version=raw.get("version", 1),
        risk_profile=raw.get("risk_profile"),
        style=raw.get("style", ""),
        lang=raw.get("lang", "en"),
        universe=Universe(
            markets=universe_raw.get("markets", ["US", "TW"]),
            exclude=universe_raw.get("exclude", []),
        ),
        caps=Caps(
            position_pct=caps_raw.get("position_pct", 10),
            position_hard_pct=caps_raw.get("position_hard_pct", 25),
            theme_pct=caps_raw.get("theme_pct", 20),
            max_adverse_excursion_pct=caps_raw.get("max_adverse_excursion_pct", -15),
            book_vol_target_pct=caps_raw.get("book_vol_target_pct"),
            exemptions=exemptions,
        ),
        turnover=Turnover(
            hurdle=turnover_raw.get("hurdle", 0.15),
            verdict_floor=turnover_raw.get("verdict_floor", "neutral"),
            max_swaps_per_week=turnover_raw.get("max_swaps_per_week", 2),
        ),
        friction=Friction(
            tw_roundtrip_pct=friction_raw.get("tw_roundtrip_pct", 0.585),
            us_roundtrip_pct=friction_raw.get("us_roundtrip_pct", 0.02),
        ),
        notify=Notify(channels=notify_raw.get("channels", [])),
        philosophy=philosophy,
        extra={k: v for k, v in raw.items() if k not in _KNOWN_TOP_KEYS},
    )


def validate(ips: IPS) -> list[str]:
    """Human-readable list of problems with `ips`. Empty list = valid."""
    problems: list[str] = []

    if ips.version != 1:
        problems.append(f"unsupported version: {ips.version!r} (expected 1)")

    if ips.risk_profile is not None and ips.risk_profile not in _KNOWN_RISK_PROFILES:
        problems.append(
            f"unknown risk_profile: {ips.risk_profile!r} (expected one of {sorted(_KNOWN_RISK_PROFILES)})"
        )

    c = ips.caps
    if not (0 < c.position_pct <= c.position_hard_pct <= 100):
        problems.append(
            f"caps: expected 0 < position_pct ({c.position_pct}) <= "
            f"position_hard_pct ({c.position_hard_pct}) <= 100"
        )
    if not (0 < c.theme_pct <= 100):
        problems.append(f"caps.theme_pct ({c.theme_pct}) must be in (0, 100]")

    # The allocator compares a price against entry x (1 + mae/100), so the sign is the
    # whole meaning: written unsigned (15) every position is already "past" it, written
    # at or beyond -100 no position ever can be. Type first, and separately, so a
    # wrong-*type* value is not reported against a range its own printed value meets (T18).
    mae = c.max_adverse_excursion_pct
    if isinstance(mae, bool) or not isinstance(mae, (int, float)):
        problems.append(
            f"caps.max_adverse_excursion_pct ({mae!r}) must be a number, not {type(mae).__name__}"
        )
    elif not (-100 < mae < 0):
        problems.append(
            f"caps.max_adverse_excursion_pct ({mae}) must be a negative percent in (-100, 0) — "
            f"it is a loss from entry, so e.g. -15 for 15% below entry"
        )

    # None = off; a set value is an annualized percent like theme_pct, not signed like
    # the MAE threshold above (it's a vol level, not a loss).
    if c.book_vol_target_pct is not None and not (0 < c.book_vol_target_pct < 100):
        problems.append(
            f"caps.book_vol_target_pct ({c.book_vol_target_pct}) must be a percent in (0, 100), or unset"
        )

    for exemption in c.exemptions:
        if exemption.cap not in _CAP_FIELDS:
            problems.append(
                f"exemption for {exemption.ticker!r} references unknown cap field "
                f"{exemption.cap!r} (expected one of {sorted(_CAP_FIELDS)})"
            )

    if not (0 < ips.turnover.hurdle < 1):
        problems.append(f"turnover.hurdle ({ips.turnover.hurdle}) must be in (0, 1)")

    # the allocator adds these to the hurdle as friction/100, so a bad value doesn't just
    # crash — nan makes the gate accept every gap, inf reject every gap, and a negative
    # buys swaps the user's own hurdle refuses. At 100% round-trip cost the score-equivalent
    # is 1.0, already the widest gap two 0..1 scores can have, so the gate is dead above it.
    # The type test comes first: `0 <= "0.585" < 100` raises rather than returning False.
    for f in ("tw_roundtrip_pct", "us_roundtrip_pct"):
        v = getattr(ips.friction, f)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 <= v < 100):
            problems.append(f"friction.{f} ({v!r}) must be a percent in [0, 100)")

    if ips.turnover.verdict_floor.lower() not in VERDICT_ORDER:
        problems.append(
            f"turnover.verdict_floor: unknown verdict {ips.turnover.verdict_floor!r} "
            f"(expected one of {VERDICT_ORDER})"
        )

    if not ips.universe.markets:
        problems.append("universe.markets must not be empty")
    else:
        for m in ips.universe.markets:
            if not (isinstance(m, str) and 2 <= len(m) <= 3 and m.isalpha()):
                problems.append(f"universe.markets: {m!r} doesn't look like a market code")

    return problems
