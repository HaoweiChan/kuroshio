# Contributing

## Dev setup

```bash
git clone <this repo>
cd kuroshio
uv venv && uv pip install -e ".[yfinance,agents,dev]"   # or: pip install -e ".[yfinance,agents,dev]"
.venv/bin/ruff check .
.venv/bin/pytest tests/ -q
```

Drop `agents` from the extras if you're not touching the LLM research pipeline —
it pulls in langchain/langgraph and needs no API key just to install.

## Design ethos

- **Pure compute, thin IO.** Screening/scoring/allocation are pure functions over
  plain data. IO lives in `providers/` and `cli.py`, not in core logic.
- **Providers are plugins.** Core never imports a data vendor. New data source →
  new provider behind `MarketDataProvider`, not a new `if` branch in core.
- **Graceful degradation over faked values.** Missing data drops the affected
  factor and renormalizes the rest, and says so in the output. It never
  silently zero-fills or invents a number.
- **Deletion over addition.** No speculative abstractions, no config knob for a
  value that isn't varying yet. If it's not load-bearing today, it doesn't go in.
- **Proposals only, never execution.** The engine emits `ProposalCard`s and
  stops there — this is both a product decision and a regulatory line. PRs
  that add order execution (brokerage APIs, order placement, anything that
  moves money) will be closed without review.

## PR policy

I'm the sole maintainer and I review this against my own roadmap, not against
demand — a PR being useful to you doesn't mean it lands. No commitment to
feature requests, including reasonable ones. Small, focused PRs with tests
have the best odds of getting merged quickly; large PRs that touch multiple
concerns will sit.

Adding a new market? Follow `docs/adding-a-market.md` — it covers the profile
shape, Stage-1 gates, and factor scoring conventions new markets need to match.

## Bug reports

Include: a minimal repro, your Kuroshio/Python/OS versions, and the exact
command you ran. Reports without a repro are hard to act on and may sit
until someone (possibly you) supplies one.
