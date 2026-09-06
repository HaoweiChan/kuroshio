---
id: TASK-13
title: '`kuroshio book` and `kuroshio site`: the book builder and the static site as generic CLI, user data outside the repo'
status: In Progress
assignee: []
created_date: '2026-09-06 03:10'
labels: []
dependencies: []
references:
  - TASK-11
  - TASK-12
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's daily book (screen top-N → ledger ratings veto → IPS weights → propose → NAV sizing →
static site) runs today as private scripts under `~/.kuroshio/bin` (2026-09-06), hard-wired to one
owner: a broker file from another tool, a personal IPS path, Chinese-only labels, a design-system
stylesheet lifted from `docs/index.html` by absolute path. The owner's ask: make the mechanism a
generic feature any user can run on their own holdings and reports, and keep every byte of user
data (holdings, NAV, reports, the site) outside the repo.

Two subcommands, pure functions over files the user already has:

1. `kuroshio book --screen <screen.json> --ratings <ratings.jsonl> --ips <ips.md> [--nav N]
   [--positions <positions.json|csv>] [--pm-size <json>] [--locked <json>] --out <dir>`
   Core-N / per-theme cap / attack overflow / percent-risk × PM multiplier / rating TTL and
   earnings expiry / owner-locked names — the rules in `~/.kuroshio/bin/build_book.py`, moved to
   `core/book.py` with the numbers as options (defaults: 15 core, 3 per industry, 3 attack, 5%
   base, 15% attack budget, 45-day TTL, 21-day review). `--positions` is a plain
   `symbol,quantity,market_value,average_price` table so any broker export fits; no other tool's
   paths inside the repo. Writes `holdings.yml`, `book.json`, `book.md`, `alloc.md`, `propose.out`.
2. `kuroshio site --book <dir> --reports <dir> --out <dir> [--lang en|zh]`
   The four page types (book, allocation, report index, report) in `docs/index.html`'s design
   system, with the stylesheet packaged as a resource (`kuroshio/site/style.css`, and
   `docs/index.html` reads the same file so the two cannot drift). Labels from a small string
   table keyed by `lang` (default from the IPS `lang`). Relative links only; atomic swap of the
   output dir. No server — a static tree the user serves however they like.

Out of scope: the cron, launchd and tailscale glue (owner-specific, stays in `~/.kuroshio/bin`),
and any broker API.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli book --screen tests/fixtures/screen.json
--ratings tests/fixtures/ratings.jsonl --ips examples/ips-balanced.md --nav 100000 --out /tmp/b &&
PYTHONPATH=. .venv/bin/python -m kuroshio.cli site --book /tmp/b --reports tests/fixtures/reports
--out /tmp/s` (budget: one run, under 20 s, no network) produces `index.html`, `alloc.html`,
`reports.html` and one report page, and `git status` shows nothing new under the repo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `kuroshio book` reproduces the owner's 2026-09-04 book (same 18 names, same weights) from the same screen, ratings, IPS, NAV and positions files, with every path passed as an option and nothing read from a fixed location.
- [ ] #2 `kuroshio site` renders the four page types from a fixture book and a fixture report tree; the stylesheet is one packaged file that `docs/index.html` also uses.
- [ ] #3 `--lang en` and `--lang zh` both render every label; unknown lang falls back to en.
- [ ] #4 `.gitignore` covers the default output names, and a test asserts no fixture contains a real NAV, broker symbol list or absolute path.
- [ ] #5 `docs/`/README document the two commands in one paragraph each, with the disclaimer that the output is mechanical, not advice.
<!-- AC:END -->
