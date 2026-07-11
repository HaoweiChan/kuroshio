# Kuroshio build plan

Master plan lives in the maintainer's vault (open-core: user IPS content and business glue
never enter this repo). This file tracks the engine's build state only.

## Phase 2 — engine repo (current)

- [x] Repo bootstrap: Apache 2.0 + NOTICE (TradingAgents attribution), package skeleton, shared types
- [x] `providers/` — base ABC + yfinance (default, zero-key) + finmind (TW)
- [x] `core/screening/` — TW momentum-breakout + US leadership profiles (ported from production)
- [x] `core/ips/` — schema v1, parser, validate, three example presets
- [x] `core/allocator/` — challenger-vs-incumbent proposal engine
- [x] `agents/facets/` — facet TTL cache (engine-agnostic store)
- [x] `cli.py` — screen / propose / ips-validate (verified live against yfinance)
- [x] `agents/engine/` — TradingAgents componentization (fresh copy, personal traces stripped,
      portfolio-state provider injected, `agents` optional extra)
- [ ] Wire facets ↔ engine: replace engine's own facet_cache JSON store with `agents/facets`
      FacetStore, or document why both exist (currently two cache implementations)
- [ ] `kuroshio research TICKER` CLI subcommand driving TradingAgentsGraph
- [ ] examples/quickstart.md + docker-compose (self-host acceptance: clean machine, one command)
- [ ] README with real architecture diagram + Phase-1 run data (pre-launch)

## Later phases (not in this repo yet)

- server/ + client/ + docker-compose (hosted + self-host one-click)
- backtest framework
- integrations/discord (proposal card → webhook)

## Non-goals (permanent)

- Order execution — the engine only ever proposes.
- Multi-tenant/billing glue — open-core boundary.
