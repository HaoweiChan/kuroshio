---
id: TASK-11
title: 'Trailing stop: Panel high/low, ATR ratchet on invalidation_price, MAE on the minimum close'
status: PR
assignee: []
created_date: '2026-09-06 01:00'
labels: []
dependencies: []
references:
  - DRAFT-26
  - DRAFT-28
  - DRAFT-37
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked (2026-09-06) that stops move up as price rises and that this run unattended,
inside the daily `propose` pass. Three deferrals close together: DRAFT-26 (`Panel` has no
high/low, so no true range and no ATR), DRAFT-28 (a `trend_add` has no drawdown trigger) and
DRAFT-37 (`caps.max_adverse_excursion_pct` compares the latest price, not the minimum close
since entry, so a weekly runner misses the decision the key exists to force).

Design, in `core/allocator/engine.py` step 3 and `core/allocator/signals.py`:

1. `Panel` gains `high` and `low`; both providers (`providers/yf.py`, `providers/finmind.py`)
   populate them; screening and backtest keep working unchanged.
2. A ratchet: for a `trend_add` always, and for a `pullback_add` once the running high has
   cleared entry + 2R (R = entry − recorded invalidation), the live invalidation becomes
   `max(recorded, running_high_since_entry − caps.trail_atr_mult × ATR14)`, never lowered.
   `caps.trail_atr_mult` is a new IPS key, default 3, validated in `core/ips/parser.py`.
3. Every ratchet move is appended to the ledger (date, ticker, old, new) so `evaluate` scores
   the stop that was live on each date, not the final one.
4. MAE uses the minimum close since `entry_date`: a position that fell −25% and recovered to
   −5% still gets its DECIDE card.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips examples/ips-balanced.md
--holdings ~/.kuroshio/book/latest/holdings.yml --market us --universe-file
~/.kuroshio/universe.txt` (budget: one run, under 60 s) prints a ratcheted invalidation for
any holding whose running high has cleared entry + 2R, and none for the others.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `Panel` carries high/low from both providers; existing screen and backtest tests pass.
- [x] #2 `trend_add` and cleared `pullback_add` holdings get `invalidation_price = max(recorded, running_high − caps.trail_atr_mult × ATR14)`, never lowered — one test per setup_type and one for the never-lower rule.
- [x] #3 every ratchet move is appended to the ledger with date, ticker, old and new; `evaluate` reads the live stop at each date.
- [x] #4 `caps.max_adverse_excursion_pct` compares the minimum close since `entry_date`; the −25% then −5% case still gets a DECIDE card.
- [x] #5 DRAFT-26, DRAFT-28 and DRAFT-37 are closed as superseded by this task (status: Superseded, `superseded_by: TASK-11`, with a Resolution section each).
<!-- AC:END -->
