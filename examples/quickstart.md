# Quickstart: 10 minutes to first health check

**Status: pre-release.** Kuroshio is not yet published to PyPI; APIs and CLI flags
will change without notice. This walks through everything from an empty clone
to your first screen, IPS check, proposal, and (optionally) LLM research run.

## Install

From a clone of this repo:

```bash
# full install (screeners + LLM research engine + dev/test tools)
pip install -e ".[yfinance,agents,dev]"

# minimal install (screen/propose/ips-validate only — no LLM deps)
pip install -e ".[yfinance,dev]"
```

`yfinance` is the zero-key US/TW data provider extra; `agents` pulls in the
LangGraph-based multi-agent research engine (only needed for `kuroshio research`).

## 1. Screen — zero API keys

Ranks breakout candidates with yfinance data, no account or key required:

```bash
kuroshio screen --market us --tickers NVDA,AMD,AVGO,MSFT,META,LLY,XOM,JPM,COST,NFLX
```

`us` is 12-1 momentum since 2026-09; the previous leadership screen is `--market
us-leadership`.

## 2. Validate an Investment Policy Statement

```bash
kuroshio ips-validate examples/ips-balanced.md
```

## 3. Propose — rebalance against your IPS

Write a small `holdings.yml`:

```yaml
- {ticker: AAPL, weight: 0.08, theme: tech, score: 0.55}
- {ticker: XOM, weight: 0.22, theme: energy, score: 0.30}
```

Then:

```bash
kuroshio propose --ips examples/ips-balanced.md --holdings holdings.yml --market us
```

`XOM` above pushes the `energy` theme past this IPS's 20% theme budget, so
expect an ALERT card. Add `--candidates candidates.yml` (same `ticker`/
`final_score` shape, plus optional `theme`/`verdict`) to also get SWAP
proposals against challengers.

## 4. Research — LLM multi-agent analysis for one ticker

Requires the `agents` extra (above) **and** an LLM API key. The engine
defaults to OpenAI (`OPENAI_API_KEY`); it also speaks any OpenAI-compatible
endpoint, including OpenRouter — set `KUROSHIO_LLM_PROVIDER=openrouter` and
`OPENROUTER_API_KEY` to swap providers with no other config. See
`kuroshio/agents/engine/default_config.py` for the full list of `KUROSHIO_*`
overrides (models, provider, thinking effort, output language, etc.).

```bash
export OPENAI_API_KEY=sk-...
kuroshio research AAPL --market us
```

Runs the market/sentiment/news/fundamentals analyst team, the bull/bear
debate, risk discussion, and portfolio manager, then writes a report tree
(`complete_report.md` plus per-section markdown) under `./reports/AAPL/<date>/`
and prints the report path and a one-line verdict (Buy/Overweight/Hold/
Underweight/Sell).

Useful flags: `--lang zh-TW` for localized report sections, `--analysts
market,news` to run a subset, `--date YYYY-MM-DD` to backfill, `--out DIR` to
change the report root, `--no-cache` to force every analyst to rerun (see below).

### The facet-cache cost story

Each analyst's report is cached per ticker per day ("facets"); a daily rerun
only regenerates analysts whose facet is stale (fundamentals get a 7-day TTL,
everything else invalidates daily), so re-running `research` on the same
ticker the same day costs a fraction of the first run instead of a full
LLM pass every time.
