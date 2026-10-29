---
id: TASK-27
title: 'book emits a reduction ticket for a cash withdrawal'
status: PR
assignee: []
created_date: '2026-10-29'
labels: []
dependencies: []
references:
  - TASK-24
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner withdraws cash from the Schwab account from time to time. The
book already sizes on the vault NAV, so targets shrink on their own once the debit lands; what is
missing is the sell list that raises the cash first.

Change: `kuroshio book --withdraw <usd>` (with `--positions`/`--nav` as today) writes `reduction.md`
beside `alloc.md`: cash needed = withdraw − the positions file's `cash`; sell that fraction pro-rata
of every non-locked, non-option long position, whole shares rounded up per name, with approx dollar
value and the total. Locked names (the `--locked` JSON) are excluded and the others scale up to cover. Output
only — no orders, no broker calls; execution stays with the owner (kuroshio never touches the
Schwab token, hermes owns it). Rejects a withdraw larger than the sellable total.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli book --help` shows `--withdraw`; run once on a fixture positions file, budget $0 · reps 1 — reduction.md totals ≥ the cash needed and lists no locked name.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 on a fixture account, `--withdraw` yields per-name share counts whose proceeds plus existing cash are ≥ the withdraw amount and within one share per name of it — a test.
- [ ] #2 a locked name and an option position never appear in the ticket; a withdraw above the sellable total exits non-zero with a message — tests.
- [ ] #3 without `--withdraw`, book output is byte-identical to today.
<!-- AC:END -->
