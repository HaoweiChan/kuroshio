---
version: 1
risk_profile: balanced
style: "momentum breakout, cyclical-aware, diversified across markets"
lang: en
universe:
  markets: [US, TW]
  exclude: []
caps:
  position_pct: 10
  position_hard_pct: 25
  theme_pct: 20
  max_adverse_excursion_pct: -15  # forced decision at 15% below entry
  # book_vol_target_pct: 15  # opt-in. Through the allocator on 12-1 top-20 (docs/backtest-2026-09.md
  #   §E): 2021-2026 drawdown -29% -> -16% for -54 pts of return through 2025; 2014-2021 no drawdown
  #   change for -74 pts. Set it only if the drawdown is the number you are managing.
  exemptions: []
turnover:
  hurdle: 0.15
  verdict_floor: neutral
  max_swaps_per_week: 2
friction:
  tw_roundtrip_pct: 0.585
  us_roundtrip_pct: 0.02
notify:
  channels: [discord]
---

This portfolio optimizes for participating fully in strong trends while still
capping the damage any single mistake can do. A 10% standard position lets
winners matter; a 25% hard ceiling stops a winner from quietly becoming the
whole portfolio's risk. Themes are budgeted at 20% effective exposure so a
crowded trade (three names riding the same catalyst) gets flagged before it
turns into concentration risk in disguise. A position 15% below its entry stops
being a background holding: it gets a card asking for kill, add, or a rewritten
thesis, because the mistake that compounds is the one nobody looked at again.

The turnover hurdle sits at a moderate 15 points, and the verdict floor is
`neutral` rather than `overweight` — this IPS trusts the quant score gap to do
the deciding, using qualitative research mainly as a veto (no `sell`/
`underweight` names get proposed) rather than a second bar to clear. Up to two
swaps a week keeps the portfolio responsive without letting churn eat the
edge to friction.

This refuses to hold a name purely on inertia once a materially better
challenger clears the hurdle — "I've held it a while" is not a reason.
Override toward more caution around earnings season or macro event risk, when
score gaps are noisier than usual and a swap now may just be reacting to
one bad print.

The book targets 15% annualized volatility: when the trailing 20-session
realized vol of the whole portfolio runs hotter than that, exposure scales
down pro rata rather than staying fully invested through a spike (§E of
docs/backtest-2026-09.md — this cut the 2021-2026 max drawdown from -33% to
-14%, at the cost of about 30 points of out-of-sample return).
