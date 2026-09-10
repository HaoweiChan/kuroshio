---
id: TASK-15
title: 'kuroshio book emits the needs-research list as JSON for the desk'
status: In Progress
assignee: []
created_date: '2026-09-09'
labels: []
dependencies: []
references:
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-09)
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The hermes desk is retiring its old TradingAgents crons and will run `kuroshio research` only on names kuroshio says need it: screen top-N names with no live rating (none, expired at the earnings print, or past the TTL) and held names due for re-review (rating older than the review age or a print within the warning window). Today that list exists only as prose inside `alloc.md`. `kuroshio book` writes it as `needs_research.json` next to `book.json`: `{"asof": ..., "research": [{"ticker", "rank", "reason": "not researched | rating void: earnings 2026-10-15 after rating 2026-09-05 | rating 24 days old | earnings in 5 days", "rating_date": ...}]}`, ordered by rank, held names first, so the desk can cap the count and feed the tickers to `research` without parsing markdown.

Probe: none — library/CLI output read by the desk; the fixture book in tests is the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `kuroshio book` writes `needs_research.json` beside `book.json` with the four reasons above, held names first then by rank; `alloc.md` renders from the same list.
- [ ] #2 a test with one unrated top-N name, one rating voided by an earnings print, one 24-day-old held rating and one held name 5 days before its print yields exactly those four entries with those reasons.
- [ ] #3 an empty list writes `{"research": []}`, never a missing file.
<!-- AC:END -->
