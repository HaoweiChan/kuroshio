---
id: TASK-10
title: 'Session-mode research: engine dataflows over MCP, reasoning by the Claude session'
status: Done
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

Cost control is part of the task, not a follow-up: session mode moves spend from an API bill to the owner's subscription quotas (Claude: Opus/Fable and Sonnet; Codex: Terra and Sol), and those are finite too. The skill therefore routes by role and caps by run: (1) the four analysts, the bull/bear round and the three risk views run on the cheap tier — Sonnet subagents on Claude, or the Codex rescue agent on Sol when the owner prefers Codex — never on Opus/Fable or Terra; (2) only the trader proposal and the portfolio-manager decision run on the session's own (heavy) model, and each is a single call; (3) one debate round and one risk round, no retries beyond one per role; (4) a per-run budget in the skill's frontmatter (max subagents, max tool calls per subagent, max names per invocation — default 5) that the skill must print at the start and stop at when hit; (5) the facet cache is honoured, so a name researched today is not re-fetched; (6) `record_rating` carries `model` (the tier that made the decision) beside `source`, so `evaluate` can later show whether the cheap and heavy tiers disagree in hit rate. The paid API path is never called from the skill — that is the whole point.

Precedent: on 2026-09-05 five SOXX/NDX entrants (ASX, NBIS, UMC, STM, MTSI) were rated this way by hand — dataflows called from Python, reasoning in the session, rows written with `source: claude-session`.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth (MCP server: one test that lists tools and calls `get_fundamentals` against a stub provider; the skill is prose)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 the skill's frontmatter declares the role→tier routing and the per-run budget; a dry read of the skill shows analysts/debate/risk on the cheap tier and only trader + PM on the session model; `record_rating` rows carry `model`
- [x] #2 `kuroshio mcp` starts, lists the tools above, and `record_rating` appends a row `evaluate` reads with a `source` field; the skill, run in a Claude Code session on one ticker, produces `5_portfolio/decision.md` with a `**Rating**:` line the ledger parser accepts and no OpenRouter/OpenAI call is made (assert via an env guard that fails the run if `KUROSHIO_LLM_PROVIDER` is used).
<!-- AC:END -->
