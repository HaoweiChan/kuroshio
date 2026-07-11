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
kuroshio screen --market us --top 20
kuroshio ips-validate examples/ips-balanced.md
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

Apache 2.0. Includes components derived from
[TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache 2.0) — see NOTICE.

## Disclaimer

Kuroshio is a software tool. It produces research reports and rule-triggered proposals from
**your own** rules (IPS) and **your own** API keys. It is not investment advice, and it never
places orders.
