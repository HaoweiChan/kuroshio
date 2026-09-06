---
id: TASK-14
title: 'Report page after the TradingAgents viewer: hero, tabs, lenses, debates, decision trail'
status: PR
assignee: []
created_date: '2026-09-06 21:40'
labels: []
dependencies:
  - TASK-13
references:
  - TASK-13
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner (2026-09-06) prefers the per-report layout of the earlier TradingAgents JSON viewer
(a React single page, kept outside this repo) over `kuroshio site`'s one-column dump of
`complete_report.md`, and wants that layout with this repo's palette unchanged. The viewer's
shape, reproduced here without React and without JSON: a report hero (kicker, large ticker,
file name; verdict block on the right with the rating in the rating colour and the date), a
tab bar (Overview · Research · Debates · Decision · Raw), and per tab:

- Overview: a two-column grid — main: a thesis card (the PM's Executive Summary) with a top
  accent rule, then a coverage grid (one tile per role file present: market, sentiment, news,
  fundamentals, bull, bear, manager, trader, aggressive, neutral, conservative, decision;
  present tiles carry an accent top rule, absent ones are dimmed); rail: a verdict card
  (rating, ticker · date, reference close) and a three-cell signal strip (stop · target ·
  R:R from close), then a sizing/next-earnings compact card.
- Research: a numbered section intro, then one collapsible card per analyst file
  ("Lens 01 · Market" …), each card's body split into content blocks at `## ` headings when
  there are two or more (the viewer's PanelizedMarkdown).
- Debates: two groups side by side on wide screens — 01 Research desk: bull (accent rule),
  bear (sell rule), research manager (fg rule); 02 Risk committee: aggressive (accent),
  neutral (muted), conservative (sell), portfolio manager (fg).
- Decision: numbered stages — research plan (manager), trader decision, final decision
  (PM), the last with the fg rule.
- Raw: the existing complete_report.md rendering.

Inputs are the role files already on disk (`1_analysts/*.md`, `2_research/*.md`,
`3_trading/trader.md`, `4_risk/*.md`, `5_portfolio/decision.md`); a report tree that only
has `complete_report.md` renders Raw and an empty-state panel on the other tabs. Tabs and
card collapse are a few lines of inline JS with no dependency; every colour comes from the
existing `docs/style.css` tokens (`--accent` for bull/positive, `--sell` for bear/negative,
`--warn` for neutral/hold, `--fg` for decision) — no new colours, no fonts. Labels through
`kuroshio/site/labels.py` for both languages. Report index and the other three page types
are unchanged.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli site --book /tmp/b --reports
tests/fixtures/reports --out /tmp/s` after the task-13 probe's `book` run (budget: one run,
under 20 s, no network) produces `reports/AAA/2026-01-02.html` containing the five tab
buttons, a thesis card, a coverage grid with twelve tiles, and both debate groups; `git
status` shows nothing new.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 the report page has the hero, the five tabs and the four tab bodies described above, built from the role files; a fixture with all twelve role files renders twelve present tiles, a fixture with only complete_report.md renders Raw plus empty-state panels.
- [x] #2 tone rules use only existing tokens: bull/aggressive → --accent, bear/conservative → --sell, neutral → --warn, manager/PM/final → --fg; a test greps the page for hex colours and finds none outside the shared stylesheet.
- [x] #3 a role file with two or more `## ` sections renders as a grid of content blocks, one section each; a single-section file renders as one block.
- [x] #4 every new label exists in both `en` and `zh`; the existing label-parity test covers them.
- [x] #5 index, alloc and reports pages are byte-identical to task-13's output for the same inputs.
<!-- AC:END -->
