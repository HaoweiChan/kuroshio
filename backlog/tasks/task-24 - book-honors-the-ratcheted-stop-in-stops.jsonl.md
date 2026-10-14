---
id: TASK-24
title: 'book honors the ratcheted stop in stops.jsonl'
status: PR
assignee: []
created_date: '2026-10-14'
labels: []
dependencies: []
references:
  - TASK-18
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The book's stop veto (`kuroshio/core/book.py`, `stopped_out` and the "below its stop" check in
`walk`) only knows the rating's `stop_loss`. The actual-portfolio pass ratchets held names' stops
upward by ATR and appends each move to the ledger's `stops.jsonl` (`ledger.STOPS`, rows
`{date, market, ticker, old, new, reason}`), and fires EXIT on that ratcheted line. The book never
reads it, so a name the owner just exited on the ratcheted stop stays in (or comes back to) the
book the next day. Observed on the owner's 2026-10-13 book: a held name whose stop the ratchet
had raised well above its rating's `stop_loss` closed under the ratcheted line, got an EXIT card,
and stayed in the book at full weight.

Change: the stop the book vetoes on is the stop **in effect on each session**:
`max(rating stop_loss, newest stops.jsonl `new` for that ticker and market whose row date is on
or after the rating date and strictly before that session)`. A close at or below the stop in
effect that session is a stop-out → the existing skip `"{rating} stopped out {date}; needs a new
rating"` (the existing phrase stays; it may append the stop value). Today's "below its stop" check
uses the stop in effect today. Rows dated before the rating date are ignored, so a newer rating
re-arms the name exactly as today. A close that was above the stop in effect on its own day is
never a stop-out retroactively, even if the stop was later ratcheted above it.

`cmd_book` loads `ledger.ledger_dir() / ledger.STOPS` best-effort, filtered to `--market`, the
same way `_logged_stops` does (an unreadable ledger warns on stderr and the book builds as
before); `build_book` takes the rows as a new optional argument (`None` → today's behavior).

Not changed: sizing (`target_weight` still sizes on the rating stop), the `invalidation_price` the
book writes to holdings.yml, propose, the ratchet itself, stops.jsonl writes, the vendored
`kuroshio/agents/engine`.

Probe: `T=$(mktemp -d); cp -R ~/.kuroshio/ledger $T/ledger; mkdir -p $T/book/2026-10-12; cp ~/.kuroshio/book/2026-10-12/book.json $T/book/2026-10-12/; KUROSHIO_LEDGER_DIR=$T/ledger PYTHONPATH=. <main-checkout>/.venv/bin/python -m kuroshio.cli book --market us --screen ~/.kuroshio/screen/2026-10-13.json --ratings ~/.kuroshio/ledger/ratings.jsonl --scores ~/.kuroshio/ledger/scores.jsonl --ips ~/.kuroshio/ips-us.md --meta ~/.kuroshio/book/meta.json --pm-size ~/.kuroshio/book/pm_size.json --locked ~/.kuroshio/book/locked.json --themes ~/.kuroshio/book/themes.json --provider yfinance --lang zh --out $T/book/2026-10-13; echo rc=$?; grep -o '[A-Z]* *[A-Za-z]* \(below its stop\|stopped out\)[^"]*' $T/book/2026-10-13/alloc.md $T/book/2026-10-13/book.md | head` · budget $0, one yfinance fetch of ~80 names, under 90 s · reps 1 — rc=0, and the name exited on its ratcheted stop on 2026-10-12 is skipped (`below its stop` or `stopped out`) at the ratcheted level, in neither core nor attack. Real holdings: the PR states the outcome only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a test in tests/test_book.py on a fictional ticker: rating stop 80 (rated 2026-09-05), stops rows ratcheting to 110 on 2026-10-02, close 109.5 on 2026-10-12 → the name is skipped `stopped out 2026-10-12; needs a new rating`; the same fixture without stops rows keeps the name (today's behavior).
- [ ] #2 tests: a close above the stop in effect on its day but below a later ratcheted stop is not a stop-out; stops rows dated before the rating date are ignored (a newer rating re-arms the name); rows of another market or ticker are ignored.
- [ ] #3 `kuroshio book` reads stops.jsonl from the ledger dir; an unreadable or missing file warns (or is silent when absent) and the book still builds; pre-existing tests pass unedited.
<!-- AC:END -->
