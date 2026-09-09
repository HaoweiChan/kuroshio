---
id: TASK-20
title: 'propose names positions with no session price as a separate ALERT and exits 3 when it is blind'
status: PR
assignee: []
created_date: '2026-09-10'
labels: []
dependencies: []
references:
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-10)
  - TASK-11
  - TASK-18
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen 2026-09-10 on the first actual-portfolio pass: a yfinance rate limit left every one of the 17
held names without a session price. `propose` exited 0 and folded all 17 into the "not fully
monitored" coverage line, in the same voice as "NVDA has no setup_type", so AMZN sitting under its
ratcheted stop produced no breach ALERT and nothing said the run had not compared anything.
Once the desk's intraday risk check reads `stops.jsonl` for its stop line, that silence turns into a
stop that is *stale* rather than wrong, with no signal to fall back on.

Change, in `core/allocator/engine.py` and `cli.py`:

1. A dedicated ALERT card whenever any holding has no price for the session: "Price data missing
   for N of M positions this session — no stop, trend or loss rule was compared for: <tickers>.
   Their last ratcheted stops stay in force but were not checked today." It is emitted before the
   coverage line and the missing names are not repeated there.
2. `kuroshio propose` exits 3 (new, documented) when *no* holding has a session price — the run
   was blind; 0 otherwise. `_run_propose` still writes whatever cards it has.
3. The daily cron (outside the repo) writes `actual/status.json` `{asof, exit, prices_missing: [...]}`
   from the exit code and the card, so the desk reads one file to decide stale vs. checked.

Probe: `KUROSHIO_LEDGER_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips
~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/actual/holdings_us.yaml --market us
--universe-file ~/.kuroshio/universe.txt --provider <a provider stub that returns an empty panel>`
(budget: one run, under 30 s) prints the missing-price ALERT naming all 17 tickers and exits 3;
the same command with the real provider exits 0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a holding with no session price is named on a dedicated missing-price ALERT (count, tickers, "stops stay in force but were not checked today") and is not also listed on the coverage line for that reason; holdings with prices are unaffected — one test each.
- [ ] #2 `propose` exits 3 when no holding has a session price and 0 when at least one does; the exit codes are documented in the CLI help/README; a test covers each branch.
- [ ] #3 the ratchet appends nothing and the MAE/thesis rules emit nothing for a priceless holding (no false "never-lower" write from a missing bar), with a test.
<!-- AC:END -->
