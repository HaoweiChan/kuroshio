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
edge to friction. Those 15 points are index percentile points only when
`propose` is run with `--universe-file`; otherwise they are percentile points
of your own holdings + candidates files, a coarser scale.

This refuses to hold a name purely on inertia once a materially better
challenger clears the hurdle — "I've held it a while" is not a reason.
Override toward more caution around earnings season or macro event risk, when
score gaps are noisier than usual and a swap now may just be reacting to
one bad print.
