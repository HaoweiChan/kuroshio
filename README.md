# Kuroshio

> **TradingAgents for your whole portfolio — run it on your holdings daily, not one ticker once.**

Named after the Kuroshio — the Pacific current that carries apex predators past Taiwan.

Kuroshio is an open-source **quantamental portfolio engine**:

- **Screen** — multi-factor momentum screeners (US, TW) with cross-sectional percentile scoring
- **Research** — LLM agent research per holding, facet-cached so daily runs cost cents, not dollars
- **Propose** — IPS-driven challenger-vs-incumbent rebalancing **proposals** (the engine never executes trades)

**Status: pre-release.** Not yet published; APIs will change without notice.

## Quickstart

```bash
pip install -e ".[yfinance,dev]"

# rank breakout candidates (zero API keys — yfinance default)
kuroshio screen --market us --tickers NVDA,AMD,AVGO,MSFT,META,LLY,XOM,JPM,COST,NFLX

# check a policy file
kuroshio ips-validate examples/ips-balanced.md

# proposal cards: your holdings vs challengers, governed by your IPS
printf -- '- {ticker: AAPL, weight: 0.08, theme: tech, score: 0.55}\n- {ticker: XOM, weight: 0.22, theme: energy, score: 0.30}\n' > holdings.yml
kuroshio propose --ips examples/ips-balanced.md --holdings holdings.yml --market us
```

Full walkthrough (including the LLM research pipeline): [examples/quickstart.md](examples/quickstart.md).

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Maintenance & support

Self-hosted engine, provided as-is — no SLA. Issues and PRs are triaged
against the maintainer's roadmap on maintainer time, not on demand; see
[CONTRIBUTING.md](CONTRIBUTING.md). Security reports are the exception and
always take priority; see [SECURITY.md](SECURITY.md).

## License

Apache 2.0. Includes components derived from
[TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache 2.0) — see NOTICE.

## Disclaimer

Kuroshio is a software tool. It produces research reports and rule-triggered proposals from
**your own** rules (IPS) and **your own** API keys. It is not investment advice, and it never
places orders.
