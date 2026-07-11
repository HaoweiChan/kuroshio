# Kuroshio build plan

Master plan lives in the maintainer's vault (open-core: user IPS content and business glue
never enter this repo). This file tracks the engine's build state only.

## Phase 2 — engine repo (current)

- [x] Repo bootstrap: Apache 2.0 + NOTICE (TradingAgents attribution), package skeleton, shared types
- [x] `providers/` — base ABC + yfinance (default, zero-key) + finmind (TW)
- [x] `core/screening/` — TW momentum-breakout + US leadership profiles (ported from production)
- [x] `core/ips/` — schema v1, parser, validate, three example presets
- [x] `core/allocator/` — challenger-vs-incumbent proposal engine
- [x] facet TTL cache — engine's production-validated `graph/facet_cache.py` (a parallel
      standalone FacetStore was built, then deleted: one cache, not two)
- [x] `cli.py` — screen / propose / ips-validate (verified live against yfinance)
- [x] `agents/engine/` — TradingAgents componentization (fresh copy, personal traces stripped,
      portfolio-state provider injected, `agents` optional extra)
- [x] `kuroshio research TICKER` CLI subcommand driving TradingAgentsGraph
- [x] examples/quickstart.md
- [x] `core/backtest` — walk-forward harness + `kuroshio backtest` (survivorship caveat documented)
- [ ] docker-compose (self-host acceptance: clean machine, one command — lands with server/)

## Pre-launch checklist (repo public = launch)

- [ ] Squash history into a single initial-release commit (fresh-history rule; dev history
      references private projects)
- [ ] README with architecture diagram + real daily-run track record
- [ ] Register kuroshio.io; claim PyPI/npm `kuroshio` (0.0.1 placeholder)
- [ ] Two weeks of the maintainer's own portfolio running on this engine

- [x] `integrations/discord` — proposal cards → webhook (propose `--discord-webhook`)

## Later phases (not in this repo yet)

- server/ + client/ + docker-compose (hosted + self-host one-click)

## Non-goals (permanent)

- Order execution — the engine only ever proposes.
- Multi-tenant/billing glue — open-core boundary.
