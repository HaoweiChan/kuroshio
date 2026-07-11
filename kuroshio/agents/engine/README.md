# kuroshio.agents.engine

Multi-agent LLM trading-analysis pipeline, componentized from a private fork
of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
(Apache License 2.0 — see the repo-root `LICENSE` and `NOTICE`).

Analysts (market/chip/sentiment/news/fundamentals), the bull/bear researcher
debate, risk-management debators, and the portfolio manager run as a
LangGraph pipeline (`graph/trading_graph.py`, entry point
`TradingAgentsGraph`). Additions on top of upstream, carried over unmodified:

- **Facet cache** (`graph/facet_cache.py`): per-ticker analyst-report cache so
  a daily rerun skips analysts whose report is still fresh.
- **TW market support**: chip analyst, TAIFEX/FinMind dataflows, single-stock
  futures sizing (`dataflows/tw/`, `portfolio/sizing_tw.py`).
- **i18n**: zh-TW glossary for presentation-layer output (`config/i18n/`,
  `agents/utils/i18n.py`).

## What's excluded

This is the engine only — delivery and portfolio-account integrations are
downstream concerns, not componentized here:

- Webhook/payload delivery (a downstream notification integration, not engine logic).
- Personal portfolio-state providers and allocators tied to specific broker
  accounts. `TradingAgentsGraph` instead takes an optional constructor-injected
  `portfolio_state_provider` — anything with `.load() -> PortfolioSnapshot | None`
  — so callers can plug in their own account integration; `None` (the default)
  runs with an empty snapshot.
- CLI glue (`main.py`, `pipeline_runner.py`) — a kuroshio-native entry point
  is written separately.

Config env vars use the `KUROSHIO_*` prefix (see `default_config.py`).
