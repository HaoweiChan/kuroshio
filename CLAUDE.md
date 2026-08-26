# Kuroshio — repo notes for Claude

Open-source quantamental portfolio engine. Python 3.11+, pandas + pyyaml core;
`kuroshio/agents/engine` is vendored (componentized TradingAgents) — ruff
excludes it; never reformat it.

## Gate

Run from the repo root, in order; all must pass:

1. `ruff check .` — zero errors.
2. `pytest tests/ -q` — all tests pass, zero failures.

Dev env: the main checkout's `.venv` (`pip install -e ".[agents,yfinance,dev]"`);
worktrees have no venv of their own — use `/Users/willy/Documents/kuroshio/.venv/bin/`.
