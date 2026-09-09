---
id: TASK-16
title: 'a held name rated Sell or Underweight gets a DECIDE card, never an automatic swap'
status: To Do
assignee: []
created_date: '2026-09-09'
labels: []
dependencies: []
references:
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-09)
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agreed with the hermes desk on 2026-09-09: the TA verdict on an incumbent does not enter the swap hurdle or verdict floor (rating hit rate is unmeasured until `evaluate` has 60+ sessions), it is a veto. Today a Sell/Underweight rating on a held name changes nothing in `propose` — the verdict is only read for challengers. Add step 3c to `core/allocator/engine.py`: when the newest ledger rating for a held ticker (passed in like prices/ma50, keyword-only `verdicts_held=None`, filled by `_run_propose` from `ratings.jsonl`) is at or below `underweight`, emit one DECIDE card in the MAE family: kill / rewrite thesis / hold with a written reason, quoting the rating date, model and source, and the stop the report gave. Exactly one card per ticker per run even when the MAE rule also fires (the MAE card already names the thesis ALERT; this one names the rating).

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips ~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/holdings.yml --market us --universe-file ~/.kuroshio/universe.txt` (budget: one run, under 60 s) prints a DECIDE card for every held name whose newest rating is Underweight or Sell, and none otherwise
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a held name whose newest rating is Underweight or Sell gets one DECIDE card quoting rating, date, source, model and the report stop; Hold/Overweight/Buy get nothing; a name with no rating gets nothing.
- [ ] #2 the card never triggers a SWAP by itself: with a challenger that clears the hurdle the SWAP card still quotes the score gap, not the rating.
- [ ] #3 one card per ticker per run when MAE and the rating both fire, with a test.
- [ ] #4 a rating older than the earnings print after it (same void rule as `kuroshio book`) does not count.
<!-- AC:END -->
