# Kuroshio roadmap

What the engine already does, and what is coming. Kuroshio is open-core: the engine —
screening, IPS, allocator, backtest, LLM research — is this repo. Anyone's actual IPS
content and portfolio data stay on their own machine and never enter it.

## Shipped

- **Repo bootstrap** — Apache 2.0 + NOTICE (TradingAgents attribution), package skeleton, shared types
- **`providers/`** — base ABC + yfinance (default, zero-key) + finmind (TW)
- **`core/screening/`** — TW momentum-breakout + US 12-1 momentum (default) + US leadership profiles, cross-sectional pctrank scoring
- **`core/ips/`** — IPS schema v1, parser, validate, three example presets
- **`core/allocator/`** — challenger-vs-incumbent proposal engine (theme budgets, hard caps, turnover hurdle)
- **`core/backtest`** — walk-forward harness (top-k forward returns, excess vs benchmark, rank-IC,
  score quintiles) + `kuroshio backtest`, with the survivorship-bias caveat printed on every run
- **`agents/engine/`** — componentized TradingAgents LLM pipeline, portfolio-state provider injected,
  behind the optional `agents` extra
- **Facet TTL cache** — `graph/facet_cache.py`, so a daily run over a whole portfolio costs cents.
  (A parallel standalone `FacetStore` was built, then deleted: one cache, not two.)
- **`kuroshio research TICKER`** — CLI subcommand driving `TradingAgentsGraph`
- **`integrations/discord`** — proposal cards → webhook (`propose --discord-webhook`)
- **`core/simulate`** — walk-forward portfolio simulator that runs `propose()` (sizing, swaps, trims,
  MAE) against an equal-weight baseline and the benchmark; `--members-file` gives `backtest` and
  `simulate` a point-in-time universe (`scripts/sp500_members.py`)
- **Backtest 2026-09** — [docs/backtest-2026-09.md](backtest-2026-09.md): the leadership screen has
  no cross-sectional edge and the allocator rules subtract from it; plain 12-1 momentum wins
  2021–2026 and loses 2014–2021, so it is the `us` default without being an edge (the
  leadership screen is `us-leadership`)
- **CLI** — `screen` / `backtest` / `simulate` / `propose` / `ips-validate` / `research`, stdlib argparse only
- **Genericization** — `MarketProfile` registry: adding a market is one module + one registry entry
  ([docs/adding-a-market.md](adding-a-market.md))
- **Project hygiene** — CI (ruff + pytest on 3.11/3.12/3.13), `py.typed`, CONTRIBUTING, SECURITY

## Next

- `docker-compose` self-host path: clean machine, one command
- `server/` + `client/` — a live web UI that runs the engine on demand, instead of the current
  static snapshot demo
- PyPI release of `kuroshio`

## Non-goals (permanent)

- **Order execution.** The engine only ever proposes. This is both the product position and the
  regulatory safety line.
- **Multi-tenant / billing glue.** Out of scope for the open engine.
