---
id: TASK-15
title: 'Input type validation for holdings.yml and candidates.yml'
status: In Progress
assignee: []
created_date: '2026-09-08'
labels: []
dependencies: []
references:
  - DRAFT-8, DRAFT-9, DRAFT-10, DRAFT-11, DRAFT-12, DRAFT-16, DRAFT-41 — closed by this task
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_holdings_from_yaml` and `_candidates_from_yaml` (kuroshio/cli.py) validate *key names*
and nothing else. Every other way a hand-edited YAML file can be wrong escapes as a bare
traceback, because `cmd_propose` catches only `ValueError` (cli.py:587). Seven drafts are
the same missing coercion pass, found one at a time across seven PRs; this closes them
together because they are one diff.

The one with teeth is DRAFT-41: `entry_price: "100.0"` — quoting a price is an ordinary
YAML habit — makes `_entry_price`'s `h.entry_price > 0` raise
`TypeError: '>' not supported between instances of 'str' and 'int'` for *every* position
in the file, so one quoted price takes down the whole run. The rest are the same class:

- **DRAFT-41 / DRAFT-11** — `entry_price` / `invalidation_price` stay `str` in fields
  annotated `float`, and `target_weight` does arithmetic on them.
- **DRAFT-9** — `- {ticker: AAPL}` with no `weight:` raises `TypeError` out of
  `Holding(**item)`, exit 1, not the exit-2 `error:` path the same function gives an
  unknown key.
- **DRAFT-8** — `_candidates_from_yaml` has the unknown-key half but not the missing-key
  half: bare `item["ticker"]` raises a context-free `KeyError`. `_load_yaml` also assumes
  a top-level list, so a file written as a mapping iterates as strings and dies on
  `item.get`.
- **DRAFT-10** — `entry_date` is coerced with `str()` and never validated, while
  types.py and docs/ARCHITECTURE.md both call it an ISO date; `not-a-date` is stored
  verbatim and cli.py:676 then swallows the parse failure downstream.
- **DRAFT-12** — `item.get('ticker', '?')` returns `None` when the key is present but
  null, so the error line reads `holdings.yml: None: unknown key ...` (both parsers).
- **DRAFT-16** — `Candidate.final_score` is annotated `float` while cli.py:187 stores
  `item.get("final_score")`, i.e. `None`.

Shape: one coercion pass per parser, raising `ValueError` with the existing
`f"{path}: {ticker}: ..."` prefix so everything lands on the exit-2 path that already
exists. No schema library — the two parsers are twenty lines each and the repo's IPS
schema is deliberately hand-written for the same reason.

Probe: `printf -- '- {ticker: AAPL, weight: 0.1, entry_price: "100.0", invalidation_price: "90"}\n' > /tmp/h.yml && PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips examples/ips-balanced.md --holdings /tmp/h.yml --market us --provider yfinance` (budget: one run, under 30 s) exits 0 having treated the prices as floats, or exits 2 with an `error:` line naming the file and ticker — never a traceback. Today it is a `TypeError` traceback at exit 1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 quoted `entry_price` / `invalidation_price` parse to `float`; a value that is not a number is a `ValueError` naming the file, ticker and field, not a traceback (DRAFT-41, DRAFT-11).
- [x] #2 a holdings entry missing a required key exits 2 with an `error:` line naming the missing key, not a `TypeError` traceback (DRAFT-9).
- [x] #3 a candidates entry missing `ticker` exits 2 the same way, and a YAML file whose top level is a mapping rather than a list is rejected by name instead of dying on `item.get` (DRAFT-8).
- [x] #4 `entry_date` is validated as an ISO date at parse time and a non-ISO value is rejected there, not swallowed downstream (DRAFT-10).
- [x] #5 `- {ticker: null, ...}` reports `?` rather than `None` in the error prefix, in both parsers (DRAFT-12).
- [x] #6 `Candidate.final_score` is annotated `float | None`, matching what the parser stores (DRAFT-16).
- [x] #7 each of the seven drafts has a test that goes red without its fix; the seven draft files move to `backlog/completed/`.
<!-- AC:END -->
