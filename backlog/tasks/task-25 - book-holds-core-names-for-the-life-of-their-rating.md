---
id: TASK-25
title: 'book holds core names for the life of their rating'
status: PR
assignee: []
created_date: '2026-10-14'
labels: []
dependencies: []
references:
  - TASK-24
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The attack sleeve has hysteresis (`attack_buffer`) and a hold (`attack_hold_rank`, PR #63): a
name in yesterday's sleeve is placed first and keeps its slot for its rating's life. The core
has neither — it is re-walked from the ranking every day, and because many top-ranked names are
vetoed, the last core slots go to names ranked ~50-80 whose ranks move a few places daily. Result
on the stored books 2026-09-25..2026-10-13: one name entered/left core 6 times on ranks 56-80,
two more came in for single days, with no change in rating or stop.

Change: `BookRules.core_hold_rank` (int, default 0 = off) and CLI `book --core-hold-rank N`. When
N > 0, a name in yesterday's core (`prev_book["core"]`, not an attack overflow row) whose rank
today is ≤ N is pinned like `attack_hold_rank` pins attack names: it goes down the walk before
unpinned names, so it takes its core slot before any newcomer. Every veto still applies to a
pinned name — rating void (TTL / earnings), Sell/Underweight, below its stop, stopped out, theme
budget full (all of these drop it). The per-theme cap (`core_per_theme`) and `core_n` still hold;
newcomers fill only the slots left. A pinned core name that also was a doubled (attack top-up)
name behaves as the existing attack hold already defines; do not change attack-hold behavior.

Docstring at the top of book.py gains a short **Hold** note for the core, in the same style as the
attack hold.

Not changed: default behavior with `core_hold_rank=0` (byte-for-byte same book), attack hold and
attack buffer, tier, sizing, propose, the vendored `kuroshio/agents/engine`. The cron flag is set
outside the repo after merge.

Probe: `T=$(mktemp -d); cp -R ~/.kuroshio/ledger $T/ledger; mkdir -p $T/book/2026-10-12; cp ~/.kuroshio/book/2026-10-12/book.json $T/book/2026-10-12/; KUROSHIO_LEDGER_DIR=$T/ledger PYTHONPATH=. <main-checkout>/.venv/bin/python -m kuroshio.cli book --market us --core-hold-rank 80 --screen ~/.kuroshio/screen/2026-10-13.json --ratings ~/.kuroshio/ledger/ratings.jsonl --scores ~/.kuroshio/ledger/scores.jsonl --ips ~/.kuroshio/ips-us.md --meta ~/.kuroshio/book/meta.json --pm-size ~/.kuroshio/book/pm_size.json --locked ~/.kuroshio/book/locked.json --themes ~/.kuroshio/book/themes.json --provider yfinance --lang zh --out $T/book/2026-10-13; echo rc=$?; python3 -c "import json,sys;b=json.load(open(sys.argv[1]));print(sorted(x['ticker'] for x in b['core']))" $T/book/2026-10-13/book.json` · budget $0, one yfinance fetch of ~80 names, under 90 s · reps 1 — rc=0 and the name that was core on 2026-10-12 but rank 80 and "below cut" on 2026-10-13 without the hold is in the core list. Real holdings: the PR states the outcome only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a test in tests/test_book.py: core_n slots full, yesterday's core name now ranked below all of today's qualifying newcomers but ≤ core_hold_rank stays in core and the lowest-ranked newcomer is out; with core_hold_rank=0 the same fixture gives today's result.
- [ ] #2 tests: a held core name that is vetoed (Underweight, stopped out, rating void) or ranked > core_hold_rank is not kept; the per-theme cap still holds with pinned names.
- [ ] #3 `kuroshio book --core-hold-rank` is wired through cmd_book; pre-existing tests pass unedited.
<!-- AC:END -->
