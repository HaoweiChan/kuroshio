# Kuroshio build plan

Master plan lives in the maintainer's vault (open-core: user IPS content and business glue
never enter this repo). This file tracks the engine's build state only.

## Phase 2 — engine repo (current)

- [x] Repo bootstrap: Apache 2.0 + NOTICE (TradingAgents attribution), package skeleton, shared types
- [ ] `providers/` — base ABC + yfinance (default, zero-key) + finmind (TW)
- [ ] `core/screening/` — TW momentum-breakout + US leadership profiles (ported from production)
- [ ] `core/ips/` — schema v1, parser, validate, three example presets
- [ ] `core/allocator/` — challenger-vs-incumbent proposal engine
- [ ] `agents/facets/` — facet TTL cache (engine-agnostic store)
- [ ] `cli.py` — screen / propose / ips-validate
- [ ] `agents/` — TradingAgents engine componentization (fresh copy, personal traces stripped,
      portfolio-state provider injected; ~10K LOC, langgraph as optional extra)
- [ ] README with real architecture diagram + Phase-1 run data (pre-launch)

## Later phases (not in this repo yet)

- server/ + client/ + docker-compose (hosted + self-host one-click)
- backtest framework
- integrations/discord (proposal card → webhook)

## Non-goals (permanent)

- Order execution — the engine only ever proposes.
- Multi-tenant/billing glue — open-core boundary.
