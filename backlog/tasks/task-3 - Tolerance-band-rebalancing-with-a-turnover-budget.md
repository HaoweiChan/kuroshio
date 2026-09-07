---
id: TASK-3
title: Tolerance-band rebalancing with a turnover budget
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies:
  - TASK-2
references:
  - TODO.md T9
  - docs/backtest-2026-09.md §2 — "task-1 and task-3 wait for one [a signal]"
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the binary hard-cap TRIM with Daryanani-style relative bands: flag when a position
drifts outside ±band_rel (default 20%) of its target weight, propose trading back to the
band edge (not to target), ranked by drift severity, subject to the existing
max_swaps_per_week style turnover budget.

TASK-1 (target weight) is done, so nothing technical blocks this — but
docs/backtest-2026-09.md §2 does: every allocator rule tested so far *subtracts* from the
ranking it manages (a 6–25 point tax on `us`), so a new rebalancing rule is refining the
management of a signal that has no measured edge. It waits on TASK-2 for that signal, and
is then judged by the same bar the report set: beats equal-weight top-k of the same ranker
in both windows.

Depends (TODO.md ids): T7

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 position at 12.5% vs 10% target with band 20% yields a card whose proposed weight is the band edge (12%); position at 11% yields none; band and budget read from IPS.
- [ ] #2 `simulate` over both backtest windows shows the band rule is not a tax: it beats equal-weight top-k of the same ranker, or the result is recorded and the rule is not shipped on.
<!-- AC:END -->
