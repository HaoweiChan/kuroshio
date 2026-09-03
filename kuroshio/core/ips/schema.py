"""IPS schema — nested dataclasses mirroring docs/ARCHITECTURE.md `core/ips` section.

Boring by design: no metaprogramming, no pydantic. `parser.py` builds these
field-by-field from a parsed YAML dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERDICT_ORDER = ["sell", "underweight", "neutral", "overweight", "buy"]


def _rank(v: str) -> int:
    v = v.lower()
    # the LLM agents' scale names the middle rung "Hold" (agents/engine/agents
    # /schemas.py PortfolioRating) — same rung as the IPS's "neutral", not a sixth.
    return VERDICT_ORDER.index("neutral" if v == "hold" else v)


def verdict_at_least(v: str, floor: str) -> bool:
    """True if verdict `v` is at least as bullish as `floor` (case-insensitive).

    Unknown verdicts (either side) never clear the bar.
    """
    try:
        return _rank(v) >= _rank(floor)
    except (ValueError, AttributeError):
        return False


@dataclass
class CapExemption:
    ticker: str
    cap: str  # name of the Caps field this exemption relaxes, e.g. "position_hard_pct"
    reason: str = ""


@dataclass
class Caps:
    position_pct: float = 10
    position_hard_pct: float = 25
    theme_pct: float = 20
    # What one position may lose before its invalidation price stops it, as a percent of
    # NAV. Not a ceiling on weight like its neighbours — it is the input the allocator's
    # percent-risk cap turns *into* one, over the entry-to-invalidation distance
    # (allocator/engine.py:target_weight). 1% of NAV per position is the classic default.
    # Not in `_CAP_FIELDS` either: an exemption would relax a risk budget, not a cap.
    risk_budget_pct: float = 1
    # How far a position may go against its entry before the allocator forces a decision
    # (kill / add / rewrite). A cap like its neighbours — a limit on one position — and a
    # percent like them too, but signed, because it is a loss and not a ceiling: -15 is
    # 15% below entry. Deliberately not in `_CAP_FIELDS`: a per-ticker exemption from it
    # is exactly the silent hold the card exists to refuse.
    max_adverse_excursion_pct: float = -15
    exemptions: list[CapExemption] = field(default_factory=list)


@dataclass
class Universe:
    markets: list[str] = field(default_factory=lambda: ["US", "TW"])
    exclude: list[str] = field(default_factory=list)


@dataclass
class Turnover:
    hurdle: float = 0.15
    verdict_floor: str = "neutral"
    max_swaps_per_week: int = 2


@dataclass
class Friction:
    tw_roundtrip_pct: float = 0.585
    us_roundtrip_pct: float = 0.02


@dataclass
class Notify:
    channels: list[str] = field(default_factory=list)


@dataclass
class IPS:
    version: int = 1
    risk_profile: str | None = None
    style: str = ""
    lang: str = "en"
    universe: Universe = field(default_factory=Universe)
    caps: Caps = field(default_factory=Caps)
    turnover: Turnover = field(default_factory=Turnover)
    friction: Friction = field(default_factory=Friction)
    notify: Notify = field(default_factory=Notify)
    philosophy: str = ""
    extra: dict = field(default_factory=dict)
