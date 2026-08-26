"""core/allocator — challenger-vs-incumbent swap PROPOSALS.

ARCHITECTURE.md design rule #1: the engine never executes trades. Every path
through `propose()` ends in a ProposalCard (SWAP / TRIM / ALERT) for a human
to act on — that's both the product position ("proposals, not a bot") and the
regulatory line (advice, not discretionary execution).

v1 logic, in order: theme-budget alerts, hard-cap trims, then challenger vs
weakest-same-or-any-theme incumbent swaps (gated by verdict floor + score
hurdle, capped at max_swaps_per_week). See docs/ARCHITECTURE.md `core/allocator`.
"""

from __future__ import annotations

from kuroshio.types import Candidate, Holding, ProposalCard


def propose(
    holdings: list[Holding],
    challengers: list[Candidate],
    ips,
    market: str,
    verdicts: dict[str, str] | None = None,
    swaps_this_week: int = 0,
    themes: dict[str, str] | None = None,
) -> list[ProposalCard]:
    # lazy: kuroshio.core.ips is a sibling module developed in parallel — importing
    # here (not at module load) keeps this package importable regardless of ordering.
    from kuroshio.core.ips.schema import verdict_at_least

    verdicts = verdicts or {}
    themes = themes or {}
    theme_cap = ips.caps.theme_pct / 100
    hard_cap = ips.caps.position_hard_pct / 100
    exempt = {(e.ticker, e.cap) for e in ips.caps.exemptions}
    theme_pct_exempt = {e.ticker for e in ips.caps.exemptions if e.cap == "theme_pct"}

    alerts: list[ProposalCard] = []
    trims: list[ProposalCard] = []

    # 1. theme budgets — effective exposure = weight x leverage, summed per theme.
    # Fix 4: a `theme_pct` exemption (e.g. RULES AM4d's 群創/面板 carve-out) removes
    # that ticker's exposure from its theme's total, same as the hard-cap TRIM step
    # already does for `position_hard_pct` exemptions below.
    exposures: dict[str, float] = {}
    for h in holdings:
        if h.theme is None or h.ticker in theme_pct_exempt:
            continue
        exposures[h.theme] = exposures.get(h.theme, 0.0) + h.weight * h.leverage
    breached = {t for t, exp in exposures.items() if exp > theme_cap}
    for theme in sorted(breached):
        exp = exposures[theme]
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                f"Theme '{theme}' effective exposure is {exp:.1%}, above your IPS theme "
                f"budget of {theme_cap:.1%}. Challengers tagged to this theme may only "
                f"swap against incumbents in the same theme until it's back under budget."
            ),
            ips_clauses=["caps.theme_pct"],
            details={"theme": theme, "exposure": exp, "cap": theme_cap},
        ))

    # 2. hard-cap breaches -> TRIM, unless explicitly exempted.
    for h in holdings:
        if h.weight <= hard_cap or (h.ticker, "position_hard_pct") in exempt:
            continue
        trims.append(ProposalCard(
            action="TRIM",
            sell=h.ticker,
            reason=(
                f"{h.ticker} is {h.weight:.1%} of NAV, above your IPS hard cap of "
                f"{hard_cap:.1%} per name. Trim it back under the ceiling."
            ),
            ips_clauses=["caps.position_hard_pct"],
            details={"weight": h.weight, "cap": hard_cap},
        ))

    # 3. challenger vs incumbent.
    held = {h.ticker for h in holdings}
    scored = [h for h in holdings if h.score is not None]
    swaps: list[ProposalCard] = []
    if not scored:
        alerts.append(ProposalCard(
            action="ALERT",
            reason=(
                "No current holding has a screener score, so no incumbent can be "
                "objectively ranked weakest — run the screener before evaluating swaps."
            ),
        ))
    else:
        used: set[str] = set()
        floor = ips.turnover.verdict_floor
        friction_field = "tw_roundtrip_pct" if market.lower() == "tw" else "us_roundtrip_pct"
        friction_pct = getattr(ips.friction, friction_field)
        # friction_pct is a percentage (0.585 == 0.585%) while hurdle and gap live in
        # score space (0..1), so /100 converts it to the score-equivalent ARCHITECTURE.md
        # asks for before it can be added to the hurdle.
        hurdle = ips.turnover.hurdle + friction_pct / 100
        # strongest challenger picks first — caller order must not decide who
        # gets the weakest incumbent
        for c in sorted(challengers, key=lambda c: c.final_score, reverse=True):
            if c.ticker in held:
                continue
            verdict = verdicts.get(c.ticker, "neutral")
            if not verdict_at_least(verdict, floor):
                continue
            theme = themes.get(c.ticker)
            same_theme_only = theme in breached
            pool = [h for h in scored if h.ticker not in used and (not same_theme_only or h.theme == theme)]
            if not pool:
                continue
            incumbent = min(pool, key=lambda h: h.score)
            gap = c.final_score - incumbent.score
            if gap < hurdle:
                continue
            used.add(incumbent.ticker)
            swaps.append(ProposalCard(
                action="SWAP",
                sell=incumbent.ticker,
                buy=c.ticker,
                reason=(
                    f"Challenger {c.ticker} scores {c.final_score:.3f} vs incumbent "
                    f"{incumbent.ticker}'s {incumbent.score:.3f} — a gap of {gap:.3f}, above "
                    f"your IPS turnover hurdle of {ips.turnover.hurdle:.3f} plus estimated "
                    f"round-trip friction of {friction_pct:.3f}%. {c.ticker}'s verdict is "
                    f"'{verdict}', at or above your floor of '{floor}'."
                ),
                ips_clauses=["turnover.hurdle", "turnover.verdict_floor", f"friction.{friction_field}"],
                score_gap=gap,
                friction_pct=friction_pct,
                details={
                    "challenger_score": c.final_score,
                    "incumbent_score": incumbent.score,
                    "verdict": verdict,
                },
            ))

    # 4. order + weekly turnover cap.
    swaps.sort(key=lambda card: card.score_gap, reverse=True)
    room = max(ips.turnover.max_swaps_per_week - swaps_this_week, 0)
    kept, suppressed = swaps[:room], swaps[room:]
    if suppressed:
        kept.append(ProposalCard(
            action="ALERT",
            reason=(
                f"{len(suppressed)} additional swap(s) cleared the hurdle but were suppressed "
                f"by your IPS turnover limit of {ips.turnover.max_swaps_per_week} swaps/week "
                f"({swaps_this_week} already made this week)."
            ),
            ips_clauses=["turnover.max_swaps_per_week"],
            details={"suppressed_count": len(suppressed)},
        ))

    return alerts + trims + kept
