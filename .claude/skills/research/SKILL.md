---
name: research
description: Research one or more tickers with the kuroshio engine's analyst/researcher/trader/risk/PM roles, reasoning in this session and pulling data over the kuroshio MCP server — no paid LLM calls. Triggers on "research TICKER", "跑 research", "評級".
routing:
  analysts: sonnet          # codex:codex-rescue on Sol when the owner asks for Codex
  bull: sonnet
  bear: sonnet
  risk: sonnet
  trader: session           # the session's own (heavy) model — Opus/Fable on Claude, Terra on Codex
  portfolio_manager: session
budget:
  max_names_per_run: 5
  max_subagents_per_name: 6
  max_tool_calls_per_subagent: 8
  debate_rounds: 1
  risk_rounds: 1
  retries_per_role: 1
---

# Research (session mode)

Runs the kuroshio engine's research roles — four analysts, bull/bear
researchers, a research manager, a trader, three risk views, a portfolio
manager — with **reasoning in this Claude Code session** and **data pulled
from the `kuroshio` MCP server**. This is the alternative to `kuroshio
research`, which costs 15-25 paid LLM calls per name. Session mode spends
this session's own subscription quota instead of an API bill (still finite
— see backlog/tasks/task-10's Cost control paragraph).

## Preconditions

1. The `kuroshio` MCP server must be connected — an entry among your
   available MCP tools, wired via `.mcp.json` at the repo root
   (`.venv/bin/python -m kuroshio.cli mcp`). If it isn't connected, stop
   and tell the owner to restart the session rather than falling back to
   any other data path.
2. **The paid path is forbidden here.** Never invoke `kuroshio research`,
   and never read or rely on `KUROSHIO_LLM_PROVIDER` or an
   OpenRouter/OpenAI key. The guarantee is structural: `kuroshio mcp` never
   imports the engine's LLM clients or graph (a test asserts it), so the
   only model that reasons in this mode is the one running this session.
3. **Print the budget before starting anything else** — echo the
   `budget:` block above. Stop research for a name the instant any cap
   would be exceeded (a sixth subagent, a second debate/risk round, a
   second retry of one role) and report what was reached and why, rather
   than quietly exceeding it. `max_names_per_run` bounds the whole
   invocation: past it, research the first N and tell the owner the rest
   were skipped for budget.

## Per ticker

For each `TICKER` (up to `max_names_per_run`), `DATE` = today unless the
owner names one, `MARKET` = `us` unless said otherwise:

0. **Facet cache check** (the session-mode analogue of the engine's
   `facets_dir` cache): if `reports/TICKER/DATE/5_portfolio/decision.md`
   already exists under `--out` (default `./reports`), skip this name —
   tell the owner it's already researched today. No re-fetch, no re-run.

1. **Data, once, in this session.** Call the MCP data tools you need
   (`get_stock_data`, `get_indicators`, `get_fundamentals`,
   `get_balance_sheet`/`get_cashflow`/`get_income_statement`,
   `get_analyst_estimates`, `get_insider_transactions`, `get_news`,
   `get_global_news`, `get_macro_indicators`) directly from this session,
   never from a subagent. Every subagent below gets the fetched text
   in its prompt and **must not call any tool itself** — this is what
   keeps the run cheap and deterministic: one shared set of facts feeds
   every role, so no subagent's own tool call can make two runs diverge.

2. **Four analysts — one message, four `sonnet` subagents** (or
   `codex:codex-rescue` on Sol, see below). Each gets the data slice its
   role needs and writes one report, mirroring the intent of
   `kuroshio/agents/engine/agents/analysts/*.py` without copying its
   prose:
   - **Market** — price/volume/indicators: trend, support/resistance,
     momentum, volatility. Ground every price/level claim in the fetched
     data; never invent a bounce or exact move that isn't in it.
   - **News** — ticker + global/macro news, FRED indicators: what moved
     the story this week and the macro backdrop.
   - **Sentiment** — news tone plus whatever sentiment signal the fetched
     data carries: bullish/bearish/neutral with a rough confidence, not a
     fabricated social-media read.
   - **Fundamentals** — fundamentals, balance sheet, cash flow, income
     statement, analyst estimates, insider transactions: valuation,
     margins, estimate-revision direction, insider buy/sell balance.

3. **Bull vs bear — one message, two `sonnet` subagents, one round**
   (`debate_rounds: 1`, `retries_per_role: 1`). Bull builds the strongest
   case from the four reports (growth, moat, positive indicators); bear
   builds the opposing case (risk, weakening position, negative
   indicators) from the same reports. One bull turn, one bear turn each
   seeing the other's argument — not a back-and-forth loop.

4. **Research manager plan — session model, short.** Read both sides and
   commit to one of the five tiers from step 7 (a plan for the trader,
   not the final rating) — reserve Hold for a genuinely balanced debate,
   not indecision. A few sentences plus the rationale.

5. **Trader proposal — session model, one call.** Turn the plan into a
   concrete Buy/Hold/Sell action with an explicit **Entry Price** and
   **Stop Loss** (long-only: never propose shorting), both anchored in
   the fetched price/indicator data.

6. **Three risk views — ONE `sonnet` subagent writes all three.** One
   call produces an aggressive view (argues for the trade, upside-first),
   a conservative view (argues caution, downside-first), and a neutral
   view (weighs both). One risk round (`risk_rounds: 1`) — no
   back-and-forth between the three.

7. **Portfolio manager decision — session model.** Synthesize the risk
   debate into the final call, in the owner's language, with exactly
   these labeled sections (this is the exact format `record_rating` and
   `kuroshio evaluate`'s ledger parser expect):
   - `**Rating**:` exactly one of Buy / Overweight / Hold / Underweight / Sell
   - `**Executive Summary**:` entry strategy, sizing, key risk levels, horizon
   - `**Investment Thesis**:` the reasoning, anchored in the debate
   - `**Stop Loss**:` a bare number (no currency symbol)
   - `**Price Target**:` a bare number

## Writing the report

Write the same tree `kuroshio/agents/engine/reporting.py:write_report_tree`
produces, under `--out` (default `./reports`), so downstream tooling (the
backtest book renderer, a human skimming the tree) reads a session-mode run
exactly like a paid one:

```
reports/TICKER/DATE/
  1_analysts/{market,sentiment,news,fundamentals}.md
  2_research/{bull,bear,manager}.md
  3_trading/trader.md
  4_risk/{aggressive,conservative,neutral}.md
  5_portfolio/decision.md
  complete_report.md   # every section above, concatenated under one header
```

Write only the files a role actually produced — a skipped role means a
missing file, not an empty one.

## Recording the rating

Call `record_rating(ticker, date, rating, stop_loss, price_target, close,
source="claude-session", model=<this session's model id>, market=MARKET)`
with the values from `5_portfolio/decision.md`. `model` is what lets
`kuroshio evaluate` compare cheap-tier vs. heavy-tier hit rates later —
never leave it blank.

## The Codex alternative

When the owner says to use Codex: run the four analysts, the bull/bear
pair, and the risk-views subagent as `codex:codex-rescue` on Sol instead of
`sonnet` — same one-message batching, same one-round debate, same budget.
The trader and portfolio manager still run on the session's own model
either way; only steps 2/3/6's tier moves.
