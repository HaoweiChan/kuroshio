---
id: TASK-17
title: 'propose --no-ledger skips the stop ledger, like screen and research'
status: In Progress
assignee: []
created_date: '2026-09-09'
labels: []
dependencies: []
references:
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-09)
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
DRAFT-50, promoted: since `#26` every `propose` run appends each ratchet move to `stops.jsonl`. `screen` and `research` have `--no-ledger`; `propose` does not, so a dry run, a probe or the hermes desk previewing a book cannot avoid writing state, and a preview run today can log a stop the live run then reads back as already ratcheted. `propose --no-ledger` reads the ledger (so the never-lower rule still holds) but appends nothing and says so on stderr.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --no-ledger --ips ~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/holdings.yml --market us --universe-file ~/.kuroshio/universe.txt` (budget: one run, under 60 s) leaves `~/.kuroshio/ledger/stops.jsonl` byte-identical (or still absent)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `propose --no-ledger` reads `stops.jsonl` for the last logged stop but appends nothing, and stderr says the moves were not recorded.
- [ ] #2 without the flag behaviour is unchanged; one test per branch.
- [ ] #3 DRAFT-50 is closed as promoted to this task.
<!-- AC:END -->
