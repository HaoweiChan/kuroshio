---
id: DRAFT-65
title: 'quoted weight and final_score still traceback at exit 1'
status: Draft
assignee: []
labels:
  - debt
dependencies: []
references:
  - PR #33 R2
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-15 gave `entry_price` / `invalidation_price` a `float()` coercion onto the exit-2
`error:` path, because those are the fields its seven drafts named. The same quoted-number
habit on the other two numeric fields still escapes as a bare traceback at exit 1:

- `weight` (holdings) reaches `engine.py:191` `h.weight * h.leverage` →
  `TypeError: can't multiply sequence by non-int of type 'float'`
- `final_score` (candidates) reaches `engine.py:539` `c.final_score - incumbent.score` →
  `TypeError: unsupported operand type(s) for -: 'str' and 'float'`

Raised as R2 in PR #33's call-1 review and not repaired there: the orchestrator confirmed
exit 1 at both `f4f85ce` (before) and `4372a22` (after), so it is pre-existing rather than
a regression, and no TASK-15 acceptance criterion names these two fields.

Repro (fails today):
`printf -- '- {ticker: AAPL, weight: "0.08", theme: tech, score: 0.55}\n' > /tmp/hw.yml && PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips examples/ips-balanced.md --holdings /tmp/hw.yml --market us`

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `test_holdings_from_yaml_coerces_quoted_weight` green — a quoted `weight` and a quoted `final_score` coerce to `float`, and a non-numeric one is a named `ValueError` on the existing exit-2 path.
<!-- AC:END -->
