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

## Tasks

Task state lives in Backlog.md (`backlog/`): one file per task, `drafts/` hold
debt, `completed/` holds merged work. `backlog task list --ready --plain` shows
what is unblocked; `backlog task view <id> --plain` shows one task. Deliver a
task with `/pr-loop <id>` (groundwork pr-loop v4, GW-017): implement → gate →
probe → one independent verification → one repair → one delta verification,
never more than two model calls; a finding blocks only with a reproduction.
Every task needs a `Probe:` line (a live command with a budget, or `none — <reason>`).

## Commits and PRs

Commit subjects and PR titles share one shape: `<type>(<scope>)?: <lowercase
summary>` (feat, fix, docs, chore, refactor, test, perf, ci, build, revert).
`.githooks/commit-msg` enforces it after `git config core.hooksPath .githooks`;
CI runs `.github/pr_check.py` on every PR. PR bodies follow
`.github/PULL_REQUEST_TEMPLATE.md`: keep all six sections, write `none` rather
than deleting one.
