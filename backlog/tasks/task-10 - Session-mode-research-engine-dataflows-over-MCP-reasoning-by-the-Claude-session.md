---
id: TASK-10
title: 'Session-mode research: engine dataflows over MCP, reasoning by the Claude session'
status: To Do
assignee: []
created_date: '2026-09-05'
labels: []
dependencies:
  - TASK-8
references:
  - kuroshio/agents/engine/dataflows (the tool surface to expose)
  - kuroshio/core/ledger.py (the rating row a session run must still write)
  - TASK-6 (ledger), TASK-8 (estimates/insider tools)
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`kuroshio research` costs 15–25 paid LLM calls per name (40 names on 2026-09-04 ≈ US$10–25 through OpenRouter). When the owner asks a Claude Code session to research names, the reasoning should run *in that session* (already paid for) and only the data should come from the engine. Add `kuroshio mcp` — a stdio MCP server exposing the engine's dataflows as tools (`get_stock_data`, `get_indicators`, `get_fundamentals`, `get_analyst_estimates`, `get_insider_transactions`, `get_news`, `get_global_news`, `get_macro_indicators`, plus `screen` and `propose` as read-only tools) and one write tool, `record_rating(ticker, date, rating, stop_loss, price_target, source="claude-session")`, which appends the same `ratings.jsonl` row `kuroshio research` writes. Ship a `.claude/skills/research/SKILL.md` that walks the session through the engine's roles (four analysts → bull/bear → trader → three risk views → portfolio manager, five-tier rating, long-only levels) using those tools, writes the same `reports/<TICKER>/<date>/` tree (`5_portfolio/decision.md`, `complete_report.md`), and ends with `record_rating`. The paid path stays as is for cron; `evaluate` can then compare hit rates by `source`.

Precedent: on 2026-09-05 five SOXX/NDX entrants (ASX, NBIS, UMC, STM, MTSI) were rated this way by hand — dataflows called from Python, reasoning in the session, rows written with `source: claude-session`.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth (MCP server: one test that lists tools and calls `get_fundamentals` against a stub provider; the skill is prose)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `kuroshio mcp` starts, lists the tools above, and `record_rating` appends a row `evaluate` reads with a `source` field; the skill, run in a Claude Code session on one ticker, produces `5_portfolio/decision.md` with a `**Rating**:` line the ledger parser accepts and no OpenRouter/OpenAI call is made (assert via an env guard that fails the run if `KUROSHIO_LLM_PROVIDER` is used).
<!-- AC:END -->
