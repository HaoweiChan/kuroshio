---
id: TASK-21
title: 'book emits candidates.yml so the actual-portfolio propose pass gets challengers'
status: PR
assignee: []
created_date: '2026-09-14'
labels: []
dependencies: []
references:
  - TASK-18
  - hermes session "TA cron 整合與 kuroshio 掛鉤" (2026-09-09)
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Agreed with the hermes desk on 2026-09-09: the actual-portfolio `propose` pass runs on the owner's
real holdings "with the book's names as challengers". Today it runs with none — `kuroshio book`
writes `holdings.yml` (the book as a holdings file) but nothing `propose --candidates` can read, so
the actual pass can ratchet stops and raise DECIDE cards but can never issue a SWAP. Rotation is
left to the owner reading book.md by hand.

`kuroshio book` writes `candidates.yml` beside `holdings.yml`, in the exact shape
`_candidates_from_yaml` already reads:

- one row per `core` + `attack` name (not `locked` — an owner-locked position is not a challenger);
- `ticker`;
- `final_score`: the screen row's `final_score` for that ticker — the same number `scores.jsonl`
  holds for it on the screen date, so it is on the incumbents' scale (the cron fills holdings'
  `score` from `scores.jsonl`);
- `verdict`: the book row's `rating` as written (`Hold` already ranks as `neutral`);
- no `theme` key: the book's themes are yfinance industry names, the desk's holdings use its own
  theme vocabulary, and writing one would make the theme-budget rule compare mismatched labels as
  if they were the same.

An empty book writes `[]`. `write_book` returns the new path with the others. The loader, the
engine and the vendored `kuroshio/agents/engine` are not touched. The cron change
(`--candidates <book>/candidates.yml` on the actual pass) lives outside the repo and follows this task.

Probe: `OUT=$(mktemp -d) && KUROSHIO_LEDGER_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m kuroshio.cli book --market us --screen ~/.kuroshio/screen/latest.json --ratings ~/.kuroshio/ledger/ratings.jsonl --scores ~/.kuroshio/ledger/scores.jsonl --ips ~/.kuroshio/ips-us.md --meta ~/.kuroshio/book/meta.json --pm-size ~/.kuroshio/book/pm_size.json --locked ~/.kuroshio/book/locked.json --lang zh --out $OUT && PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips ~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/actual/holdings_us.yaml --market us --candidates $OUT/candidates.yml --no-ledger` · budget $0, two yfinance fetches of at most ~40 names, under 90 s · reps 1 — `candidates.yml` lists every core+attack ticker in `$OUT/book.json` with its screen score; `propose` exits 0 with no `error:` line; the SWAP cards it prints are recorded (zero is a valid outcome when no gap clears the hurdle).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `kuroshio book` writes `candidates.yml` with one `{ticker, final_score, verdict}` row per core+attack name (no locked names, no `theme`), `final_score` equal to the screen row's; an empty book writes `[]`; `write_book` returns the path.
- [ ] #2 the file loads through `_candidates_from_yaml` unchanged, and a test runs `_run_propose` (or `propose`) with a holdings file whose weakest scored incumbent sits more than the hurdle below a book name and gets a SWAP card naming that pair; a book name already held gets no SWAP.
- [ ] #3 README's actual-portfolio paragraph names `candidates.yml` and `propose --candidates` in one sentence; no vendored file changes.
<!-- AC:END -->
