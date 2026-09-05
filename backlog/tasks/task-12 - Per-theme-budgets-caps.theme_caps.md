---
id: TASK-12
title: 'Per-theme budgets: caps.theme_caps overrides theme_pct for the themes it names'
status: In Progress
assignee: []
created_date: '2026-09-06 01:30'
labels: []
dependencies: []
references: []
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked (2026-09-06) to write a budget for one theme (a locked position the book does
not resize, ~15% of NAV) into the IPS. Today `caps.theme_pct` is a single budget for every
theme, so the only ways to express "this theme may hold X%" are to move every theme's budget
or to exempt the ticker entirely — neither says what the owner means.

`caps.theme_caps: {theme: pct}` replaces `theme_pct` for the themes it names and leaves the
rest under `theme_pct`. The theme-budget ALERT quotes the clause that bound
(`caps.theme_caps.<theme>` or `caps.theme_pct`). Parser validates each value in (0, 100].

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips <ips with theme_caps>
--holdings <holdings with one theme over its own cap and under theme_pct> --market us`
(budget: one run, under 10 s) prints exactly one theme ALERT naming `caps.theme_caps.<theme>`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `caps.theme_caps` parses to a dict, defaults to empty, and `validate` rejects a value outside (0, 100] or of the wrong type.
- [x] #2 a theme named in `theme_caps` alerts against its own budget and a theme not named still alerts against `theme_pct`; the card's `ips_clauses` names the clause that bound.
- [x] #3 the three example IPS files are unchanged and still validate.
<!-- AC:END -->
