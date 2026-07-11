---
version: 1
risk_profile: aggressive
style: "momentum breakout, high conviction, fast rotation"
lang: en
universe:
  markets: [US, TW]
  exclude: []
caps:
  position_pct: 15
  position_hard_pct: 25
  theme_pct: 30
  exemptions: []
turnover:
  hurdle: 0.10
  verdict_floor: neutral
  max_swaps_per_week: 4
friction:
  tw_roundtrip_pct: 0.585
  us_roundtrip_pct: 0.02
notify:
  channels: [discord, email]
---

This portfolio optimizes for capturing leadership early and rotating out
fast when it fades — it accepts more churn and more single-name risk in
exchange for staying close to whatever is actually working right now. A 15%
standard position size lets conviction ideas breathe; the hard ceiling still
sits at 25%, because even an aggressive book refuses to let one name become
an unhedged bet on itself. Theme budget is wide at 30% — this style expects
to be concentrated in the trend of the moment, not evenly spread.

The turnover hurdle is intentionally low at 10 points, with up to four swaps
a week: this IPS would rather pay the friction cost of being wrong quickly
than the opportunity cost of holding a stale leader. The verdict floor stays
at `neutral` — research is a veto against clearly broken names, not a brake
on rotation speed.

This refuses to average down on a name that has lost its momentum
characteristics just because it was recently a winner. Override toward fewer,
slower swaps when volatility spikes market-wide (VIX regime shift, TW
index limit-down day) — in a panic, the score gaps this IPS trusts stop
meaning what they normally mean.
