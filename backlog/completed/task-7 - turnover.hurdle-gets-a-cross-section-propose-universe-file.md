---
id: TASK-7
title: '`turnover.hurdle` gets a cross-section: `propose --universe-file`'
status: Done
assignee: []
created_date: '2026-09-04'
labels: []
dependencies: []
references:
  - docs/backtest-2026-09.md §A and §What this means, item 3
  - backlog/drafts/draft-18
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`turnover.hurdle` is a difference of two pctranks, and pctrank pins its scale to whatever pool it is handed: in `propose`'s auto-fill the pool is the user's own files (a 20-name pool makes 0.15 three rank places), while `simulate` scores the whole panel (0.15 is fifteen percentile points of the index). The backtest showed that one difference moves a five-year result from +224% to +36%. Give the hurdle a cross-section: `kuroshio propose --universe-file PATH` (a newline ticker list, or a `date,tickers` snapshot file from `scripts/sp500_members.py`, latest row) ranks holdings ∪ challengers ∪ universe in one ungated `score_names` pass, so an auto-filled score is a percentile of the index and the card says so; without the flag behaviour is unchanged and the card keeps disclosing the small pool. Document in the IPS examples and ARCHITECTURE that the hurdle is measured in percentile points of the cross-section the scores came from.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 with a stub provider and a 60-name universe file, `propose` auto-fills a challenger's score as its percentile among the 60+ names, the SWAP card names the universe file and its size instead of "your own files", and the small-pool refusal does not fire; without `--universe-file` the existing tests pass unchanged; a `date,tickers` snapshot file is accepted and its latest row used.
<!-- AC:END -->
