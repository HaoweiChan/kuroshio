---
id: TASK-18
title: 'Actual-portfolio pass: accept entry_date_source in holdings, write decision.json beside decision.md'
status: PR
assignee: []
created_date: '2026-09-09'
labels: []
dependencies: []
references:
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-09)
  - TASK-11
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agreed with the hermes desk on 2026-09-09: `propose` runs twice a day — once on the owner's
*actual* positions (the broker-side holdings file the desk writes, with the book's names as
challengers) and once on the book. The ratchet stop, thesis break, MAE and the Sell/Underweight
DECIDE card (TASK-16) therefore run on what the owner really holds; the book stays the target.
Two repo pieces are missing:

1. **`entry_date_source` in holdings.** The desk's file carries `entry_date_source:
   manifest_first_seen | snapshot_first_seen` next to `entry_date`. Today `_holdings_from_yaml`
   raises on any key it does not know, so the file cannot be read at all. Accept the key. When it
   is present and not `manifest_first_seen`, drop `entry_date` before building the `Holding` — a
   tracking start is not a fill date, and a running high that reaches back before the fill would
   ratchet the stop above the entry and breach on day one — and name the ticker on the existing
   "not fully monitored" line with the reason ("entry date is a tracking start, not a fill").
   `manifest_first_seen` and an absent key behave exactly as today.
2. **`decision.json` beside `decision.md`.** `kuroshio research` already parses the PM decision
   for `record_rating`. Write the same fields, plus the prose the desk turns into a thesis card, as
   `5_portfolio/decision.json`: `{ticker, date, market, rating, stop_loss, price_target, close,
   executive_summary, investment_thesis, source, model}` — the two prose fields are the labelled
   sections verbatim, no schema mapping. The vendored `kuroshio/agents/engine` is not touched; the
   sidecar is written from the kuroshio side after the report tree exists.

The cron wiring (second `propose` invocation reading the desk's file, `actual/propose.out`) lives
outside the repo and follows this task.

Probe: `KUROSHIO_LEDGER_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose
--ips ~/.kuroshio/ips-us.md --holdings ~/.hermes/vault/projects/portfolio/kuroshio-desk/holdings_us.yaml
--market us --universe-file ~/.kuroshio/universe.txt` (budget: one run, under 60 s) reads the
desk's 17-name file without an unknown-key error, ratchets only names whose entry date is a
manifest fill, and lists the snapshot-dated names on the coverage line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a holdings row with `entry_date_source: snapshot_first_seen` loads, its `entry_date` is dropped, and `propose` names it on the "not fully monitored" line with the tracking-start reason; `manifest_first_seen` and an absent key keep the date; any other value is a `ValueError` naming the row.
- [ ] #2 `kuroshio research` writes `5_portfolio/decision.json` with the fields above whenever it writes `decision.md`; `--no-ledger` still writes the sidecar; the JSON round-trips the same rating/stop/target the ledger row carries.
- [ ] #3 README documents the actual-portfolio pass and the sidecar in one paragraph each; no vendored file changes.
<!-- AC:END -->
