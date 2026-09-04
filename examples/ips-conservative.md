---
version: 1
risk_profile: conservative
style: "quality momentum, low turnover, capital-preservation first"
lang: en
universe:
  markets: [US, TW]
  exclude: []
caps:
  position_pct: 5
  position_hard_pct: 15
  theme_pct: 15
  max_adverse_excursion_pct: -10  # forced decision at 10% below entry
  # book_vol_target_pct: 15  # opt-in. Through the allocator on 12-1 top-20 (docs/backtest-2026-09.md
  #   §E): 2021-2026 drawdown -29% -> -16% for -54 pts of return through 2025; 2014-2021 no drawdown
  #   change for -74 pts. Set it only if the drawdown is the number you are managing.
  exemptions: []
turnover:
  hurdle: 0.25
  verdict_floor: overweight
  max_swaps_per_week: 1
friction:
  tw_roundtrip_pct: 0.585
  us_roundtrip_pct: 0.02
notify:
  channels: [email]
---

This portfolio optimizes for surviving to compound, not for capturing every
trend. Position sizing is deliberately tight — 5% standard, 15% hard ceiling —
because a single name, however strong the setup, should never be able to do
lasting damage to the whole. Theme exposure is capped even tighter at 15%,
because correlated bets are a bigger risk than any one ticker admits to being
on its own. The forced decision comes early too: 10% below entry, a position has
to be argued for again — killed, added to per the original plan, or given a
written new thesis. Capital preservation is mostly the discipline of not letting
a small loss become a story.

Turnover is expensive and mostly wrong, so the bar for a swap is high: a
challenger must beat the incumbent by 25 points of composite score AND already
carry an `overweight` verdict from research — not merely `neutral`. One swap a
week, at most. This refuses to chase a name on momentum alone; conviction has
to come from both the quant screen and the qualitative debate before capital
moves.

Override this IPS only for a name already held that develops a genuine
thesis break (accounting red flag, guidance cut, regime change in its
industry) — that is a risk-management exit, not a turnover decision, and the
hurdle does not apply to defense.

The book targets a tighter 12% annualized volatility — lower than the
balanced profile's 15%, in keeping with capital preservation over
participation — scaling exposure down pro rata whenever the trailing
20-session realized vol runs hotter than that (§E of
docs/backtest-2026-09.md).
