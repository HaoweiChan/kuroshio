# Kuroshio — repo notes for Claude

Open-source quantamental portfolio engine. Python 3.11+, pandas + pyyaml core;
`kuroshio/agents/engine` is vendored (componentized TradingAgents) — ruff
excludes it; never reformat it.

## Gate

Run from the repo root, in order; all must pass:

1. `ruff check .` — zero errors.
2. `pytest tests/ -q` — all tests pass, zero failures.

Dev env: a `.venv` at the main checkout's root (`pip install -e ".[agents,yfinance,dev]"`);
git worktrees have no venv of their own — run the gate via the main checkout's `.venv/bin`.
