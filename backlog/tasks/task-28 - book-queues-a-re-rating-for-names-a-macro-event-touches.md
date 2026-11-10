---
id: TASK-28
title: 'book queues a re-rating for names a macro event touches'
status: PR
assignee: []
created_date: '2026-11-09'
labels: []
dependencies: []
references: []
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A rating already dies at the first earnings print after it (the print it did not see). A macro or
industry event the rating did not see (e.g. the 2026-11-03 midterm result and the fear of a US
data-center build-out ban) is the same kind of gap, but the book has no way to hear about it.
cluegarden's graph can name the exposed tickers, including second-order ones (optics, power,
PCB) that sit under unrelated industry labels.

Change, in two parts:

1. `kuroshio book --events FILE`: a JSON list of
   `{"id": str, "date": "YYYY-MM-DD", "driver": str, "tickers": [str, ...]}`. A core or attack
   name whose `rating_date` < event `date` <= the screen date, and whose ticker the event lists,
   joins `book["review"]`, so `needs_research.json` and the alloc.md review list carry it with
   reason `event <id> (<date>) after rating <rating_date>`. The rating is NOT voided: weight,
   sleeve, stop and every other book output are unchanged — this queues a re-rating, it does not
   trade. Reason precedence for one name: earnings inside the warn window > newest matching event
   > `rating N days old`. Locked names are not the book's business and are skipped. Tickers are
   matched upper-cased. A malformed file (not a list, missing/blank id, bad date, tickers not a
   list of non-empty strings) is a `ValueError` → `cmd_book` exits 2 with the message.
   The review list's label (`review_head`, both languages) mentions macro events.

2. `.claude/skills/research/SKILL.md`: step 1 also pulls cluegarden context in-session when the
   `cluegarden` MCP server is connected — `research_context` on the name's upstream/downstream
   demand drivers and on any event that queued it — and hands the cited excerpts to the News
   analyst and the bull/bear subagent. Generated analysis is not evidence; a missing hit does not
   prove absence; cluegarden unavailable → say so in the News report and continue. Step 7: a name
   queued by an event must have its Investment Thesis address that event (exposure path, and what
   would falsify the fear).

Probe: `PYTHONPATH=. .venv/bin/python -c "import sys; from kuroshio.cli import main; sys.exit(main())" book --help` shows `--events`; one `book` run on a test fixture with an events file, budget $0 · reps 1 — needs_research.json lists the event reason and book.json weights equal the run without `--events`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 an event dated after a held name's rating and on/before the screen date puts that name in `needs_research` with the event reason; its weight and sleeve equal the run without events — a test.
- [ ] #2 an event dated on/before the rating date, after the screen date, or not listing the ticker adds nothing; earnings inside the warn window keeps its own reason — tests.
- [ ] #3 a malformed events file exits 2 with a message naming the file — a test.
- [ ] #4 without `--events`, book.json, needs_research.json, holdings.yml and candidates.yml are unchanged; only the alloc.md review heading now names macro events.
- [ ] #5 the research skill documents the cluegarden step and the event clause in the thesis.
<!-- AC:END -->
